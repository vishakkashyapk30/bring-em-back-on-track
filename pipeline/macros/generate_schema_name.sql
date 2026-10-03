{# Use the custom schema name as-is (silver, gold, features) instead of <target>_<custom>. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name is not none else target.schema }}
{%- endmacro %}
