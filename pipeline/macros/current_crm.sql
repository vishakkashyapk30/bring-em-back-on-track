{# Current CRM rows: effective_to_ts = 9999-12-31, NOT is_deleted. #}
{% macro current_crm_filter() -%}
    cast(effective_to_ts as varchar) like '9999-12-31%'
{%- endmacro %}
