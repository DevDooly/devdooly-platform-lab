"""Pure suspended Job proposal. No kubectl, image build, SQL or network calls."""
import argparse
import json
from pathlib import Path
import re

NAMESPACE='platform-lab-spark-silver-20261016'
LABELS={'devdooly.io/purpose':'iceberg-silver-trial','devdooly.io/operation':'20261016'}
POD_LABELS={**LABELS,'app.kubernetes.io/component':'spark-silver'}


def require(value,code):
    if not value:raise ValueError(code)


def resource(kind,name,spec=None,namespace=NAMESPACE,api='v1',**extra):
    value={'apiVersion':api,'kind':kind,'metadata':{'name':name,'labels':LABELS}}
    if namespace:value['metadata']['namespace']=namespace
    if spec is not None:value['spec']=spec
    value.update(extra);return value


def plan(image,snapshot,bronze_proof_sha):
    require(re.fullmatch(r'ghcr\.io/devdooly/devdooly-platform-lab-spark-silver@sha256:[a-f0-9]{64}',image),'ACTUAL_BUILT_SPARK_CANDIDATE_PIN_REQUIRED')
    require(type(snapshot)is int and 0<snapshot<2**63 and re.fullmatch('[a-f0-9]{64}',bronze_proof_sha),'ACTUAL_BRONZE_SNAPSHOT_AND_PROOF_IDENTITIES')
    container={'name':'spark','image':image,'imagePullPolicy':'IfNotPresent',
        'command':['/usr/bin/tini','-s','--','/opt/spark/bin/spark-submit','--master','local[1]','--driver-memory','1536m',
            '/opt/silver/spark_silver.py','--bronze-snapshot-id',str(snapshot)],
        'env':[{'name':'JAVA_TOOL_OPTIONS','value':'-XX:ActiveProcessorCount=1 -XX:MaxMetaspaceSize=384m -XX:ReservedCodeCacheSize=128m'},
            {'name':'SPARK_LOCAL_DIRS','value':'/tmp/spark-local'},{'name':'PYTHONHASHSEED','value':'0'},
            {'name':'HOME','value':'/tmp/spark-home'}],
        'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},
        'resources':{'requests':{'cpu':'500m','memory':'1Gi','ephemeral-storage':'256Mi'},
            'limits':{'cpu':'1','memory':'3Gi','ephemeral-storage':'3Gi'}},
        'volumeMounts':[{'name':'tmp','mountPath':'/tmp'},{'name':'work','mountPath':'/opt/spark/work-dir'},
            {'name':'secrets','mountPath':'/run/silver-secrets','readOnly':True}],
        'terminationMessagePolicy':'File'}
    pod={'serviceAccountName':'spark-silver','automountServiceAccountToken':False,'enableServiceLinks':False,
        'restartPolicy':'Never','terminationGracePeriodSeconds':120,
        'securityContext':{'runAsNonRoot':True,'runAsUser':185,'runAsGroup':185,'fsGroup':185,'seccompProfile':{'type':'RuntimeDefault'}},
        'containers':[container],'volumes':[{'name':'tmp','emptyDir':{'sizeLimit':'2Gi'}},{'name':'work','emptyDir':{'sizeLimit':'128Mi'}},
            {'name':'secrets','projected':{'defaultMode':288,'sources':[
                {'secret':{'name':'spark-silver-postgres','items':[{'key':'catalog-password','path':'catalog-password'}]}},
                {'secret':{'name':'spark-silver-s3','items':[{'key':v,'path':v} for v in ('endpoint','access-key','secret-key')]}}]}}]}
    job=resource('Job','fixed-silver-v1',{'suspend':True,'backoffLimit':0,'activeDeadlineSeconds':600,
        'template':{'metadata':{'labels':POD_LABELS,'annotations':{'devdooly.io/bronze-proof-sha256':bronze_proof_sha}},'spec':pod}},api='batch/v1')
    postgres_target={'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'platform-lab-iceberg-20261015'}},
        'podSelector':{'matchLabels':{'devdooly.io/purpose':'iceberg-jdbc-trial','devdooly.io/operation':'20261015','app.kubernetes.io/component':'postgres'}}}
    items=[resource('Namespace',NAMESPACE,namespace=None),
        resource('ResourceQuota','bounded-silver',{'hard':{'pods':'1','count/jobs.batch':'1','limits.cpu':'1','limits.memory':'3Gi',
            'requests.cpu':'500m','requests.memory':'1Gi','requests.ephemeral-storage':'256Mi','limits.ephemeral-storage':'3Gi',
            'persistentvolumeclaims':'0','services':'0','secrets':'2','configmaps':'1'}}),
        resource('ServiceAccount','spark-silver',automountServiceAccountToken=False),
        resource('NetworkPolicy','default-deny',{'podSelector':{},'policyTypes':['Ingress','Egress']},api='networking.k8s.io/v1'),
        resource('NetworkPolicy','fixed-silver-outbound',{'podSelector':{'matchLabels':POD_LABELS},'policyTypes':['Egress'],'egress':[
            {'to':[postgres_target],'ports':[{'protocol':'TCP','port':5432}]},
            {'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'platform-lab'}},'podSelector':{'matchLabels':{'app.kubernetes.io/component':'garage'}}}],
                'ports':[{'protocol':'TCP','port':3900}]},
            {'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}],
                'ports':[{'protocol':'UDP','port':53},{'protocol':'TCP','port':53}]}]},api='networking.k8s.io/v1'),
        resource('NetworkPolicy','postgres-from-spark-silver',{'podSelector':postgres_target['podSelector'],'policyTypes':['Ingress'],
            'ingress':[{'from':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':NAMESPACE}},'podSelector':{'matchLabels':POD_LABELS}}],
                'ports':[{'protocol':'TCP','port':5432}]}]},namespace='platform-lab-iceberg-20261015',api='networking.k8s.io/v1'),job]
    return {'schemaVersion':1,'status':'SUSPENDED_PROPOSAL_NOT_RUN','executionBlockedUntilNativeBronzeProofAndImageVerified':True,
        'resources':{'apiVersion':'v1','kind':'List','items':items},'runtimeSecretValuesIncluded':False,
        'runtimeNetworkPackageResolutionAllowed':False,'existingProductionResourcesModified':False,
        'requiresNewNetworkPolicyInExistingOwnedPostgresNamespace':True,'automaticApplyOrUnsuspendImplemented':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True);parser.add_argument('--bronze-snapshot-id',type=int,required=True)
    parser.add_argument('--bronze-proof-sha256',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    value=plan(args.image,args.bronze_snapshot_id,args.bronze_proof_sha256)
    with args.output.open('x',encoding='utf-8',newline='\n') as stream:json.dump(value,stream,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps({'status':value['status'],'resourceCount':len(value['resources']['items']),'serverContacted':False}))


if __name__=='__main__':main()
