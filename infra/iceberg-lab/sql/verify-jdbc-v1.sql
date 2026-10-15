-- Read-only shape/pointer projection; run against the NEW PostgreSQL database only.
SELECT table_name,column_name,data_type,character_maximum_length,is_nullable,ordinal_position
FROM information_schema.columns
WHERE table_schema='public' AND table_name IN ('iceberg_tables','iceberg_namespace_properties')
ORDER BY table_name,ordinal_position;
SELECT tablename,indexdef FROM pg_indexes
WHERE schemaname='public' AND tablename IN ('iceberg_tables','iceberg_namespace_properties')
ORDER BY tablename,indexname;
SELECT catalog_name,table_namespace,table_name,metadata_location,previous_metadata_location,iceberg_type
FROM iceberg_tables ORDER BY catalog_name,table_namespace,table_name;
SELECT catalog_name,namespace,property_key,property_value
FROM iceberg_namespace_properties ORDER BY catalog_name,namespace,property_key;
