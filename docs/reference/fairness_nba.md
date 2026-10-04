# NBA decision fairness by group

Generated 2026-10-04T09:17:07+00:00 for plan date 2026-09-28: 86,058 open cases, 51,002 scheduled. Aggregates only; groups under 10 customers are hidden and groups under 300 cases are not judged. Flag: a rate outside 0.8x to 1.25x of the overall rate. A flag means a person looks and explains it.

## Design claim

Claim: Higher break risk never raised pressure for a hardship or vulnerable customer.

- Hardship or vulnerable cases: 39,022 (39,011 customers).
- Pressure actions given to them: 0.
- Counterfactual (re-decided at break risk 0.05 and 0.95): 39,022 cases checked, 0 where high risk turned pressure on.
- Violations: 0. The claim holds.

## Overall

Pressure 38.2%, contact 61.1%, no contact 38.9%, routed to a person 41.8%, scheduled 59.3%, mean break risk 0.5224, mean expected value 149.5696.

## gender_code

| Group | Cases | Pressure | Contact | No contact | Routed | Mean risk | Mean value | Flags | Status |
|---|---|---|---|---|---|---|---|---|---|
| M | 42,043 | 38.0% (0.996x) | 60.9% | 39.1% | 42.0% | 0.5244 | 149.6439 | none | ok |
| F | 41,414 | 38.3% (1.003x) | 61.3% | 38.7% | 41.8% | 0.5206 | 149.6312 | none | ok |
| unknown | 879 | 39.0% (1.022x) | 60.4% | 39.6% | 42.4% | 0.5246 | 148.54 | none | ok |
| X | 873 | 39.3% (1.029x) | 61.4% | 38.6% | 38.7% | 0.5276 | 146.5212 | none | ok |
| U | 849 | 38.6% (1.012x) | 61.1% | 38.9% | 38.9% | 0.505 | 147.0861 | none | ok |

## age_band

| Group | Cases | Pressure | Contact | No contact | Routed | Mean risk | Mean value | Flags | Status |
|---|---|---|---|---|---|---|---|---|---|
| 25-34 | 22,779 | 38.5% (1.008x) | 61.6% | 38.4% | 41.5% | 0.5232 | 150.2018 | none | ok |
| 35-44 | 20,292 | 37.9% (0.993x) | 60.8% | 39.2% | 42.1% | 0.5228 | 149.187 | none | ok |
| 18-24 | 16,502 | 38.7% (1.013x) | 61.2% | 38.9% | 41.3% | 0.5225 | 147.3647 | none | ok |
| 45-54 | 15,860 | 38.3% (1.004x) | 61.0% | 39.0% | 41.8% | 0.5214 | 150.4214 | none | ok |
| 55-64 | 6,225 | 37.3% (0.978x) | 60.0% | 40.0% | 41.8% | 0.5138 | 146.485 | none | ok |
| 65+ | 3,974 | 36.5% (0.957x) | 61.3% | 38.7% | 44.8% | 0.5315 | 156.3776 | none | ok |
| unknown | 426 | 37.1% (0.972x) | 63.6% | 36.4% | 43.4% | 0.5476 | 169.2555 | none | ok |

## marital_status

| Group | Cases | Pressure | Contact | No contact | Routed | Mean risk | Mean value | Flags | Status |
|---|---|---|---|---|---|---|---|---|---|
| married | 26,800 | 39.1% (1.024x) | 61.2% | 38.8% | 40.3% | 0.5215 | 150.0418 | none | ok |
| single | 22,802 | 39.9% (1.045x) | 61.3% | 38.7% | 39.8% | 0.5192 | 147.57 | none | ok |
| common_law | 10,376 | 39.5% (1.035x) | 60.5% | 39.5% | 39.8% | 0.5161 | 149.0665 | none | ok |
| separated | 7,905 | 28.0% (0.733x) | 61.2% | 38.8% | 57.4% | 0.5555 | 151.6827 | pressure_rate, routing_rate | review |
| unknown | 6,867 | 38.3% (1.003x) | 61.2% | 38.8% | 41.7% | 0.5138 | 150.3479 | none | ok |
| divorced | 5,114 | 38.8% (1.017x) | 61.2% | 38.8% | 40.2% | 0.5137 | 152.2293 | none | ok |
| undisclosed | 3,715 | 37.7% (0.987x) | 59.9% | 40.1% | 40.6% | 0.5153 | 148.2762 | none | ok |
| widowed | 2,479 | 38.3% (1.004x) | 61.2% | 38.8% | 42.0% | 0.5381 | 152.5202 | none | ok |

## citizenship_status

| Group | Cases | Pressure | Contact | No contact | Routed | Mean risk | Mean value | Flags | Status |
|---|---|---|---|---|---|---|---|---|---|
| citizen | 66,280 | 38.1% (1.0x) | 61.2% | 38.8% | 41.9% | 0.5236 | 151.2388 | none | ok |
| permanent_resident | 12,461 | 38.4% (1.006x) | 61.1% | 38.9% | 41.4% | 0.5162 | 144.3272 | none | ok |
| work_permit | 3,733 | 37.6% (0.985x) | 60.1% | 39.9% | 41.6% | 0.5268 | 141.6195 | none | ok |
| study_permit | 2,695 | 39.0% (1.022x) | 60.3% | 39.7% | 40.6% | 0.5241 | 145.6821 | none | ok |
| unknown | 889 | 35.9% (0.94x) | 59.6% | 40.4% | 44.1% | 0.5025 | 143.7756 | none | ok |

## newcomer_program_flag

| Group | Cases | Pressure | Contact | No contact | Routed | Mean risk | Mean value | Flags | Status |
|---|---|---|---|---|---|---|---|---|---|
| false | 78,137 | 38.2% (1.0x) | 61.2% | 38.8% | 41.9% | 0.5226 | 150.8568 | none | ok |
| true | 7,921 | 38.1% (0.999x) | 60.2% | 39.8% | 41.3% | 0.5205 | 136.8718 | none | ok |

## accessibility_needs_flag

| Group | Cases | Pressure | Contact | No contact | Routed | Mean risk | Mean value | Flags | Status |
|---|---|---|---|---|---|---|---|---|---|
| false | 83,659 | 38.1% (0.999x) | 61.0% | 39.0% | 41.9% | 0.5225 | 149.2932 | none | ok |
| true | 2,399 | 40.1% (1.052x) | 63.4% | 36.6% | 40.5% | 0.5196 | 159.2069 | none | ok |

## vulnerability_type

| Group | Cases | Pressure | Contact | No contact | Routed | Mean risk | Mean value | Flags | Status |
|---|---|---|---|---|---|---|---|---|---|
| none | 73,946 | 44.4% (1.164x) | 60.8% | 39.2% | 33.6% | 0.5097 | 146.839 | none | ok |
| financial_hardship | 5,317 | 0.0% (0.0x) | 60.9% | 39.1% | 91.4% | 0.6004 | 156.0622 | pressure_rate, routing_rate (by design) | review |
| serious_illness | 2,238 | 0.0% (0.0x) | 63.7% | 36.3% | 93.2% | 0.6172 | 175.6346 | pressure_rate, routing_rate (by design) | review |
| mental_health | 1,510 | 0.0% (0.0x) | 64.5% | 35.5% | 92.4% | 0.5785 | 171.7815 | pressure_rate, routing_rate (by design) | review |
| domestic_situation | 1,439 | 0.0% (0.0x) | 64.8% | 35.2% | 92.8% | 0.606 | 170.8809 | pressure_rate, routing_rate (by design) | review |
| natural_disaster | 1,133 | 0.0% (0.0x) | 62.6% | 37.4% | 89.5% | 0.6255 | 172.9669 | pressure_rate, routing_rate (by design) | review |
| bereavement | 225 | 0.0% (0.0x) | 77.3% | 22.7% | 91.1% | 0.5166 | 188.0665 | none | low volume |
| cognitive_decline | 147 | 0.0% (0.0x) | 79.6% | 20.4% | 94.6% | 0.4967 | 193.669 | none | low volume |
| financial_abuse | 103 | 0.0% (0.0x) | 71.8% | 28.2% | 91.3% | 0.4404 | 180.626 | none | low volume |

## household_size

| Group | Cases | Pressure | Contact | No contact | Routed | Mean risk | Mean value | Flags | Status |
|---|---|---|---|---|---|---|---|---|---|
| unknown | 25,803 | 37.8% (0.991x) | 60.9% | 39.1% | 42.1% | 0.5266 | 149.6939 | none | ok |
| 1 | 23,849 | 38.5% (1.009x) | 61.1% | 38.9% | 41.7% | 0.5207 | 148.4291 | none | ok |
| 2 | 19,967 | 38.2% (1.0x) | 61.1% | 38.9% | 41.7% | 0.5214 | 149.3077 | none | ok |
| 3 | 11,017 | 37.9% (0.992x) | 61.3% | 38.7% | 41.8% | 0.5185 | 151.1758 | none | ok |
| 4+ | 5,422 | 38.8% (1.017x) | 61.6% | 38.4% | 42.0% | 0.5221 | 151.6953 | none | ok |

## dependants_count

| Group | Cases | Pressure | Contact | No contact | Routed | Mean risk | Mean value | Flags | Status |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 40,956 | 38.0% (0.997x) | 61.1% | 38.9% | 41.9% | 0.522 | 149.0655 | none | ok |
| unknown | 25,590 | 38.4% (1.007x) | 61.1% | 39.0% | 41.7% | 0.5228 | 149.5589 | none | ok |
| 1 | 16,496 | 38.0% (0.995x) | 60.8% | 39.2% | 41.9% | 0.521 | 149.2758 | none | ok |
| 2 | 2,772 | 38.8% (1.017x) | 62.9% | 37.1% | 41.7% | 0.5304 | 156.4036 | none | ok |
| 3 | 228 | 39.5% (1.034x) | 69.3% | 30.7% | 45.6% | 0.55 | 180.8162 | none | low volume |
| 4+ | 16 | 12.5% (0.327x) | 50.0% | 50.0% | 75.0% | 0.5739 | 130.7425 | none | low volume |
