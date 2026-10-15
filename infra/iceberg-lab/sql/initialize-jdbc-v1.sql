-- Schema derived from Apache Iceberg 1.11.0 JdbcUtil V0_CREATE_CATALOG_SQL,
-- V1_UPDATE_CATALOG_SQL and CREATE_NAMESPACE_PROPERTIES_TABLE_SQL.
-- Source: https://github.com/apache/iceberg/blob/apache-iceberg-1.11.0/core/src/main/java/org/apache/iceberg/jdbc/JdbcUtil.java
-- New dedicated database only. No IF NOT EXISTS: partial/unknown initialization must be diagnosed.
CREATE TABLE iceberg_tables (
    catalog_name VARCHAR(255) NOT NULL,
    table_namespace VARCHAR(255) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    metadata_location VARCHAR(1000),
    previous_metadata_location VARCHAR(1000),
    PRIMARY KEY (catalog_name, table_namespace, table_name)
);
ALTER TABLE iceberg_tables ADD COLUMN iceberg_type VARCHAR(5);
CREATE TABLE iceberg_namespace_properties (
    catalog_name VARCHAR(255) NOT NULL,
    namespace VARCHAR(255) NOT NULL,
    property_key VARCHAR(255),
    property_value VARCHAR(1000),
    PRIMARY KEY (catalog_name, namespace, property_key)
);
