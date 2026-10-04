{# Identity normalisation shared by every source (docs/profiling/profiling_decisions.md §2). #}

{# Upper-case, strip accents, keep letters and spaces only. #}
{% macro norm_text(x) -%}
    nullif(trim(regexp_replace(upper(strip_accents(coalesce({{ x }}, ''))), '[^A-Z ]', ' ', 'g')), '')
{%- endmacro %}

{# Last whitespace-separated token of a normalised string (handles "Van Berg" -> "BERG"). #}
{% macro last_token(x) -%}
    nullif(regexp_extract({{ norm_text(x) }}, '([A-Z]+)$', 1), '')
{%- endmacro %}

{% macro first_token(x) -%}
    nullif(regexp_extract({{ norm_text(x) }}, '^([A-Z]+)', 1), '')
{%- endmacro %}

{# Digits only; drop a leading country code 1 from 11-digit numbers. Masked digits (x) become empty. #}
{% macro phone_digits(x) -%}
    (case when length(regexp_replace(coalesce({{ x }}, ''), '[^0-9x]', '', 'g')) = 11
               and left(regexp_replace(coalesce({{ x }}, ''), '[^0-9x]', '', 'g'), 1) = '1'
          then substr(regexp_replace(coalesce({{ x }}, ''), '[^0-9x]', '', 'g'), 2)
          else nullif(regexp_replace(coalesce({{ x }}, ''), '[^0-9x]', '', 'g'), '') end)
{%- endmacro %}

{% macro postal(x) -%}
    nullif(upper(regexp_replace(coalesce({{ x }}, ''), '[^A-Za-z0-9]', '', 'g')), '')
{%- endmacro %}

{% macro to_bool(x) -%}
    (lower(cast({{ x }} as varchar)) = 'true')
{%- endmacro %}

{# Core-banking CIF: 10 digits, leading zeros restored (156,837 CIFs lost them). #}
{% macro cif(x) -%}
    lpad(trim({{ x }}), 10, '0')
{%- endmacro %}

{# Dates arrive in several formats. Slash dates: day > 12 means DD/MM, month position > 12 means MM/DD,
   otherwise DD/MM (Canadian convention); the ambiguous share is reported in the data quality report. #}
{% macro parse_date(x) -%}
    coalesce(
        try_cast({{ x }} as date),
        try_strptime(cast({{ x }} as varchar), '%Y%m%d')::date,
        try_strptime(cast({{ x }} as varchar), '%Y/%m/%d')::date,
        try_strptime(cast({{ x }} as varchar), '%b %d %Y')::date,
        try_strptime(cast({{ x }} as varchar), '%d-%m-%Y')::date,
        case
            when try_cast(split_part(cast({{ x }} as varchar), '/', 2) as int) > 12
                then try_strptime(cast({{ x }} as varchar), '%m/%d/%Y')::date
            else try_strptime(cast({{ x }} as varchar), '%d/%m/%Y')::date
        end
    )
{%- endmacro %}

{% macro parse_ts(x) -%}
    coalesce(try_cast({{ x }} as timestamp), try_strptime(cast({{ x }} as varchar), '%d/%m/%Y %H:%M:%S'),
             try_strptime(cast({{ x }} as varchar), '%Y%m%d %H%M%S'))
{%- endmacro %}
