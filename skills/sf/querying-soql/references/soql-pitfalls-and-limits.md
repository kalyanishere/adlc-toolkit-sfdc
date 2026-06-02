<!-- Parent: querying-soql/SKILL.md -->
# SOQL Syntax & Runtime Pitfalls — what AI agents get wrong

A targeted catalog of SOQL traps that produce compile-time `MALFORMED_QUERY` errors, runtime governor breaches, or silently-wrong results. Each entry shows the wrong shape, the right shape, and the rule.

Grounded in the [SOQL and SOSL Reference](https://developer.salesforce.com/docs/atlas.en-us.soql_sosl.meta/soql_sosl/) and the [Apex Developer Guide](https://developer.salesforce.com/docs/atlas.en-us.apexcode.meta/apexcode/apex_dev_guide.htm). When in doubt, treat the official guides as authoritative.

> Companion files: `soql-syntax-reference.md` (positive syntax catalog), `anti-patterns.md` (perf/bulkification anti-patterns), `query-optimization.md` (selectivity rules). This file focuses on **language-mechanics** errors specifically.

---

## SQ-01 — `SELECT *` does not exist; neither does implicit `*`

**Wrong**
```sql
SELECT * FROM Account                       -- compile error: MALFORMED_QUERY
SELECT FROM Account                         -- compile error
```

**Right** — name the fields, or use `FIELDS()`:
```sql
SELECT Id, Name, Industry FROM Account
SELECT FIELDS(STANDARD)   FROM Account LIMIT 200    -- standard fields only, ≤200
SELECT FIELDS(CUSTOM)     FROM Account LIMIT 200    -- custom fields only,  ≤200
SELECT FIELDS(ALL)        FROM Account LIMIT 200    -- all fields, hard 200-row cap
```

**Rule**: SOQL has no `*`. `FIELDS(ALL|CUSTOM|STANDARD)` does work, but `FIELDS(ALL)` carries a **hard 200-row LIMIT** — using it without `LIMIT 200` (or smaller) is a compile error. In Apex selectors, prefer explicit field lists for predictable governor cost.

---

## SQ-02 — `LIKE` is case-insensitive; the wildcard is `%`, not `*`

**Wrong**
```sql
SELECT Id FROM Account WHERE Name LIKE 'Acme*'      -- MALFORMED_QUERY: invalid wildcard
SELECT Id FROM Account WHERE Name = 'Acme%'         -- = is exact-match — % is literal here
```

**Right**
```sql
SELECT Id FROM Account WHERE Name LIKE 'Acme%'      -- starts with Acme (case-insensitive)
SELECT Id FROM Account WHERE Name LIKE '%Acme%'     -- contains Acme (slow — leading wildcard kills index)
SELECT Id FROM Account WHERE Name LIKE 'A_me'       -- single-char wildcard
```

**Rule**: `%` = any sequence; `_` = exactly one char. `LIKE` ignores case; `=` is exact match (case-sensitive on most fields, but not all — `Name`/`FirstName`/etc. are case-insensitive in `=`). Leading-wildcard `LIKE '%X%'` cannot use indexes — flag as a perf concern.

---

## SQ-03 — Date literals are tokens, not strings

**Wrong**
```sql
WHERE CreatedDate = 'TODAY'                          -- MALFORMED_QUERY
WHERE CreatedDate > '2026-01-01'                     -- works for Date, but quoted literal is fragile
```

**Right**
```sql
WHERE CreatedDate = TODAY                            -- token literal
WHERE CreatedDate >= LAST_N_DAYS:30                  -- parameterized literal
WHERE CreatedDate > 2026-01-01T00:00:00Z             -- ISO-8601 with NO quotes for DateTime
WHERE BirthDate__c = 1990-05-15                      -- ISO date literal for Date field, no quotes
```

**Rule**: SOQL date literals (`TODAY`, `YESTERDAY`, `THIS_WEEK`, `LAST_N_DAYS:n`, etc.) are **unquoted** keywords. ISO dates (`2026-01-01`) and datetimes (`2026-01-01T00:00:00Z`) are also **unquoted**. Quoting them turns them into strings → compile error.

---

## SQ-04 — `LIMIT` cap on `IN` clauses is not infinite

**Wrong**
```sql
WHERE Id IN :tenThousandIds                          -- runtime error if list > 200,000 elements
                                                      -- and severe perf issues at any large size
```

**Right** — bound IN-clause cardinality, batch when needed:
```apex
// In Apex: chunk large ID sets
for (Integer i = 0; i < ids.size(); i += 50000) {
    Set<Id> chunk = new Set<Id>();
    for (Integer j = i; j < Math.min(i + 50000, ids.size()); j++) chunk.add(ids[j]);
    query += [SELECT Id FROM Account WHERE Id IN :chunk];
}
```

**Rule**: SOQL `IN :coll` materializes the bind list into the query. Salesforce's documented practical ceiling for an `IN` list is around 200,000 elements. Beyond ~50,000 the query plan also degrades (no index use). Chunk large sets in Apex.

---

## SQ-05 — Subqueries (child relationships) need `LIMIT` and field selection — not `()`

**Wrong**
```sql
SELECT Id, (Contacts) FROM Account                   -- MALFORMED — subquery needs SELECT clause
SELECT Id, (SELECT * FROM Contacts) FROM Account     -- MALFORMED — no SELECT *
```

**Right**
```sql
SELECT Id, (SELECT Id, FirstName, LastName FROM Contacts ORDER BY LastName LIMIT 10)
FROM Account
```

**Rule**: child-relationship subqueries are full `SELECT` statements with their own field list, optional `WHERE/ORDER BY/LIMIT`. The relationship name is the **plural child relationship name** (often the object name + `s`, but custom relationships use the relationship name from the lookup field).

---

## SQ-06 — Parent traversal cap is **5 levels**

**Wrong**
```sql
SELECT Account.Owner.Manager.Manager.Manager.Manager.Name FROM Contact   -- compile error: too deep
```

**Right** — at most five `.` hops in parent traversal:
```sql
SELECT Account.Owner.Manager.Manager.Name FROM Contact
```

**Rule**: parent relationship traversal in `SELECT` and `WHERE` clauses is capped at five levels. Beyond that, you must split into multiple queries and join in Apex.

---

## SQ-07 — Subquery cap: 1 level deep, ≤ 20 child relationships per parent query

**Wrong**
```sql
SELECT Id,
       (SELECT Id, (SELECT Id FROM CaseComments) FROM Cases)             -- nested subquery — illegal
FROM Account
```

**Rule**: SOQL allows one level of subquery nesting (parent → child). You cannot nest a subquery inside a subquery. Also: a single parent query can have at most 20 distinct child-relationship subqueries.

---

## SQ-08 — `GROUP BY` requires every non-aggregated field in the SELECT to also be in the GROUP BY

**Wrong**
```sql
SELECT Industry, OwnerId, COUNT(Id) FROM Account GROUP BY Industry         -- MALFORMED — OwnerId not grouped
```

**Right**
```sql
SELECT Industry, OwnerId, COUNT(Id) FROM Account GROUP BY Industry, OwnerId
```

**Rule**: every non-aggregate field in `SELECT` must appear in `GROUP BY`. Parent-relationship fields are grouped by the relationship's full path (`Account.Owner.Name` must appear identically in both places).

---

## SQ-09 — `AggregateResult` field aliases are required for non-trivial aggregates

**Wrong**
```apex
List<AggregateResult> rs = [
    SELECT Industry, COUNT(Id), SUM(AnnualRevenue) FROM Account GROUP BY Industry
];
for (AggregateResult r : rs) {
    Object total = r.get('SUM');                  // null — no alias for SUM
}
```

**Right**
```apex
List<AggregateResult> rs = [
    SELECT Industry, COUNT(Id) cnt, SUM(AnnualRevenue) total
    FROM Account GROUP BY Industry
];
for (AggregateResult r : rs) {
    Decimal total = (Decimal) r.get('total');
    Integer cnt   = (Integer) r.get('cnt');
}
```

**Rule**: when a `SELECT` clause has multiple aggregates of the same kind or you need to read them by name, you must alias every aggregated column. Without aliases, the result map keys are unpredictable (sometimes `expr0`, `expr1`).

---

## SQ-10 — `HAVING` filters aggregated rows; `WHERE` filters input rows

**Wrong**
```sql
SELECT Industry, COUNT(Id) cnt FROM Account WHERE COUNT(Id) > 10 GROUP BY Industry   -- MALFORMED
```

**Right**
```sql
SELECT Industry, COUNT(Id) cnt FROM Account GROUP BY Industry HAVING COUNT(Id) > 10
```

**Rule**: aggregate functions can only appear in `SELECT` and `HAVING`. `WHERE` runs before grouping; `HAVING` runs after.

---

## SQ-11 — `GROUP BY ROLLUP` and `GROUP BY CUBE` are limited

```sql
SELECT Industry, Type, COUNT(Id) FROM Account GROUP BY ROLLUP(Industry, Type)
```

**Rule**: `ROLLUP` adds subtotals for each grouping level. `CUBE` adds subtotals for every combination. Both are allowed up to 3 grouping fields. Result rows include `null` for the rolled-up dimension; check for this in Apex.

---

## SQ-12 — Polymorphic relationship fields use `TYPEOF`

**Wrong**
```sql
SELECT Subject, Who.Name FROM Task                   -- works, but loses type info
SELECT Subject, Who.Phone FROM Task                  -- breaks if Who is a Lead (Lead has Phone, but type checked at runtime)
```

**Right**
```sql
SELECT Subject,
       TYPEOF Who
           WHEN Contact THEN AccountId, Email
           WHEN Lead    THEN Company, Status
           ELSE Name
       END
FROM Task
```

**Rule**: `Task.Who` and `Task.What` are polymorphic relationships (Contact|Lead, Account|Opportunity|Case|…). `TYPEOF` lets you select different fields per concrete type. Plain `Who.Name` works because every type has Name; type-specific fields require `TYPEOF`.

---

## SQ-13 — Semi-join / anti-join restrictions

**Wrong**
```sql
SELECT Id FROM Account
WHERE Id IN (SELECT AccountId, ContactId FROM AccountContactRelation)    -- MALFORMED — semi-join must select 1 field
```

**Right**
```sql
SELECT Id FROM Account
WHERE Id IN (SELECT AccountId FROM AccountContactRelation WHERE IsActive = true)
```

**Rule**: in a semi-join (`IN (subquery)`) or anti-join (`NOT IN (subquery)`), the subquery must select exactly one field. Multiple semi-joins in a single query are also limited (one per `WHERE`); use joins via relationship traversal when you need more.

---

## SQ-14 — `WITH USER_MODE` / `WITH SYSTEM_MODE` is required for explicit access control

**Wrong**
```apex
List<Account> accts = [SELECT Id, Name FROM Account];                  // no AccessLevel — implicit
```

**Right**
```apex
List<Account> accts = [SELECT Id, Name FROM Account WITH USER_MODE];   // FLS + sharing enforced
List<Account> all   = [SELECT Id, Name FROM Account WITH SYSTEM_MODE]; // bypass — document why
```

**Rule**: per project policy (`salesforce-rules.md`), every SOQL must declare an explicit `AccessLevel`. `WITH USER_MODE` is the SOQL form; `AccessLevel.USER_MODE` is the `Database` DML form. Same effect.

---

## SQ-15 — `WITH SECURITY_ENFORCED` is the older form, less powerful than USER_MODE

**Wrong** — using both:
```sql
SELECT Id FROM Account WITH SECURITY_ENFORCED WITH USER_MODE   -- MALFORMED
```

**Right**: pick one — prefer `WITH USER_MODE` (added in API 48.0+, supports DML, supports field-level errors). `WITH SECURITY_ENFORCED` only works for SOQL and throws an exception on FLS violations rather than stripping fields.

**Rule**: use `WITH USER_MODE` for new code; `WITH SECURITY_ENFORCED` is OK in legacy paths but lacks the DML and stripping features.

---

## SQ-16 — `FOR UPDATE` locks rows; not allowed with relationship subqueries or aggregates

**Wrong**
```sql
SELECT Id, (SELECT Id FROM Contacts) FROM Account FOR UPDATE     -- MALFORMED
SELECT COUNT(Id) FROM Account FOR UPDATE                         -- MALFORMED
```

**Right**
```sql
SELECT Id FROM Account WHERE Id = :accId FOR UPDATE              -- locks single row for the transaction
```

**Rule**: `FOR UPDATE` locks the returned rows so no other transaction can update them until current transaction commits. Forbidden with `ORDER BY`, aggregates, relationship subqueries, `GROUP BY`, and async/batch contexts.

---

## SQ-17 — `OFFSET` cap is **2,000**

**Wrong**
```sql
SELECT Id FROM Account ORDER BY Name LIMIT 100 OFFSET 5000    -- runtime: OFFSET cannot exceed 2000
```

**Right** — for deep pagination, use cursor / keyset:
```sql
-- Page 1
SELECT Id, Name FROM Account ORDER BY CreatedDate, Id LIMIT 100
-- Page N (use last record's value as cursor)
SELECT Id, Name FROM Account
WHERE (CreatedDate > :lastCreatedDate)
   OR (CreatedDate = :lastCreatedDate AND Id > :lastId)
ORDER BY CreatedDate, Id
LIMIT 100
```

**Rule**: `OFFSET` is hard-capped at 2000. Past that, use keyset pagination (filter on the last seen sort value). For Apex callers serving REST APIs, prefer cursor-style.

---

## SQ-18 — `WHERE` cannot reference an aggregated alias

**Wrong**
```sql
SELECT Industry, COUNT(Id) total FROM Account WHERE total > 5 GROUP BY Industry  -- MALFORMED
```

**Right** — use `HAVING`:
```sql
SELECT Industry, COUNT(Id) total FROM Account GROUP BY Industry HAVING COUNT(Id) > 5
```

(See SQ-10. Also note: `HAVING COUNT(Id) > 5` is required — `HAVING total > 5` is sometimes accepted but not portable; prefer the function form.)

---

## SQ-19 — Querying Custom Metadata Types via SOQL is anti-pattern

**Wrong**
```apex
List<MyConfig__mdt> rows = [SELECT DeveloperName, Value__c FROM MyConfig__mdt];   // unnecessary SOQL
```

**Right**
```apex
List<MyConfig__mdt> rows = MyConfig__mdt.getAll().values();                       // free, no SOQL governor
MyConfig__mdt one = MyConfig__mdt.getInstance('Default');                         // by DeveloperName
```

**Rule**: Custom Metadata Type records (`__mdt`) are accessible via free in-memory accessors that don't consume the SOQL governor. Only fall back to SOQL on `__mdt` when the accessors don't fit (e.g., dynamic filter on a non-Name field).

---

## SQ-20 — Custom Settings: `getInstance()` vs SOQL

**Right** — list-type:
```apex
MyListSetting__c row = MyListSetting__c.getValues('SomeName');     // by Name field
Map<String, MyListSetting__c> all = MyListSetting__c.getAll();
```

**Right** — hierarchy-type:
```apex
MyHierSetting__c row = MyHierSetting__c.getInstance(UserInfo.getUserId());     // user
MyHierSetting__c row = MyHierSetting__c.getInstance(UserInfo.getProfileId());  // profile
MyHierSetting__c row = MyHierSetting__c.getOrgDefaults();                       // org default
```

**Rule**: Custom Settings have free typed accessors. SOQL on a Custom Setting is rarely correct.

---

## SQ-21 — `WHERE Id = ''` and `WHERE Id != ''` are not the same as null checks

**Wrong**
```sql
SELECT Id FROM Account WHERE OwnerId != ''                       -- runtime: invalid Id format
SELECT Id FROM Account WHERE OwnerId = ''                        -- same
```

**Right**
```sql
SELECT Id FROM Account WHERE OwnerId = NULL
SELECT Id FROM Account WHERE OwnerId != NULL
```

**Rule**: `Id` and lookup fields use `= NULL` / `!= NULL` (no quotes) to test absence. Empty string `''` is invalid for an Id field. For text fields, `= ''` and `= NULL` are both valid but mean different things — the former matches blank, the latter matches null.

---

## SQ-22 — `ORDER BY` on a relationship field requires the path

**Wrong**
```sql
SELECT Id, Account.Name FROM Contact ORDER BY Account_Name        -- MALFORMED
```

**Right**
```sql
SELECT Id, Account.Name FROM Contact ORDER BY Account.Name
SELECT Id, Account.Name FROM Contact ORDER BY Account.Name NULLS FIRST
```

**Rule**: `ORDER BY` uses the dotted relationship path identically to `SELECT`. `NULLS FIRST` / `NULLS LAST` controls null sort order (default: `NULLS FIRST` for ASC, `NULLS LAST` for DESC).

---

## SQ-23 — `IN (LIST<SObject>)` works; uses Id by default

**Right**
```apex
List<Account> accts = [SELECT Id FROM Account LIMIT 10];
List<Contact> related = [SELECT Id FROM Contact WHERE AccountId IN :accts];   // SObject list as bind
```

**Rule**: when an SObject list is bound to an `IN` clause for a lookup field, SOQL extracts the `Id` of each. This is a documented convenience — avoids manually building a `Set<Id>`. Works only when the field type matches Id.

---

## SQ-24 — `ALL ROWS` includes archived/deleted rows; only on aggregate or top-level `SELECT`

**Right**
```sql
SELECT Id, Name, IsDeleted FROM Account WHERE IsDeleted = true ALL ROWS
```

**Rule**: `ALL ROWS` includes records in the Recycle Bin (deleted) and archived records (Task/Event/Case after the org's archive period). Without it, soft-deleted records are filtered out. Only allowed at the top level of the query.

---

## SQ-25 — `GROUP BY ROLLUP` returns NULL for the rollup row — beware Decimal arithmetic

**Right**
```apex
for (AggregateResult r : results) {
    String industry = (String) r.get('Industry');
    Integer cnt = (Integer) r.get('expr0');
    if (industry == null) {
        // This is the ROLLUP total row
    }
}
```

**Rule**: in `ROLLUP` results, the rolled-up dimension is `null` for the subtotal/total rows. Always null-check before using.

---

## SQ-26 — Can't query both parent and child via `relationshipName.parent` *and* `relationshipName` subquery

**Wrong**
```sql
SELECT Id, Account.Name, (SELECT Id FROM Account.Owner.Tasks)    -- nonsense path
FROM Contact
```

**Right** — separate queries, then merge in Apex.

**Rule**: relationship paths only go up (parent) or down (child via subquery), not laterally. Nested subqueries are forbidden; deep paths via parents are capped at 5.

---

## SQ-27 — `convertCurrency()` exists for multi-currency orgs

**Right** (multi-currency only):
```sql
SELECT Name, convertCurrency(AnnualRevenue) FROM Account
```

**Rule**: `convertCurrency()` converts to the user's currency. Calling it in single-currency orgs is a compile error. Use a feature check before relying on it; `UserInfo.isMultiCurrencyOrganization()` if available, otherwise check the schema.

---

## SQ-28 — `WHERE` on encrypted fields: limited operators

**Rule**: classic-encrypted (Shield) fields support a limited operator set in `WHERE`: `=`, `!=`, `IN`, `NOT IN`. `LIKE`, `>`, `<`, `>=`, `<=`, `STARTS_WITH` are not supported on probabilistic-encryption fields. Deterministic encryption supports more. Always test against an org with the same encryption scheme.

---

## SQ-29 — `LIMIT` cap is **50,000** for SOQL queries (synchronous Apex)

**Soft assumption**: "I can fetch a million records in one query." Wrong.

| Context | Total rows returned per Apex transaction | Max SOQL queries |
|---|---|---|
| Synchronous | 50,000 | 100 |
| `@future` / Queueable / Schedulable / Batch.execute | 50,000 | 200 |
| Batch.start (`Database.QueryLocator`) | 50,000,000 | 5 |
| `Database.getQueryLocator()` from non-batch | 10,000 (returns iterable lazy) | 100 |

**Rule**: 50,000 is the synchronous total-row ceiling per transaction. `Database.QueryLocator` in a Batch's `start()` lets you scan up to 50M rows. Always use Batch + QueryLocator for big scans; never assume sync can handle them.

---

## SQ-30 — `Schema.SObjectType.Account.fields.getMap()` keys are LOWERCASE

(Same gotcha as Apex AP-18; included here because it bites SOQL field-name discovery code.)

```apex
Map<String, Schema.SObjectField> fields = Account.SObjectType.getDescribe().fields.getMap();
fields.get('annualrevenue');                  // works
fields.get('AnnualRevenue');                  // null
```

**Rule**: `getMap()` keys are lowercased. Use the typed token (`Account.AnnualRevenue`) when the field name is known at compile time; if traversing dynamically, lowercase the lookup.

---

## SQ-31 — Empty `IN` clauses match nothing; not "everything"

**Wrong** assumption:
```apex
Set<Id> ids = new Set<Id>();        // empty
List<Account> a = [SELECT Id FROM Account WHERE Id IN :ids];   // returns 0 rows, not all
```

**Rule**: an empty bind to `IN` returns 0 rows. If "no filter" is the intent, omit the `WHERE` clause entirely (or guard the query in Apex with `if (ids.isEmpty()) return ...`).

---

## SQ-32 — Don't query in a loop — use `IN :collection` with a Map lookup

(Repeats `anti-patterns.md` for completeness; this is the #1 governor failure across all Apex.)

```apex
Set<Id> accountIds = new Set<Id>();
for (Contact c : contacts) accountIds.add(c.AccountId);
Map<Id, Account> byId = new Map<Id, Account>([
    SELECT Id, Name FROM Account WHERE Id IN :accountIds
]);
for (Contact c : contacts) {
    Account a = byId.get(c.AccountId);   // O(1) lookup
}
```

---

## SQ-33 — `WHERE` on Address compound fields: don't query the compound, query the parts

**Wrong**
```sql
SELECT Id FROM Account WHERE BillingAddress = '123 Main'           -- MALFORMED — compound not filterable
```

**Right**
```sql
SELECT Id FROM Account WHERE BillingStreet LIKE '123 Main%' AND BillingCity = 'SF'
```

**Rule**: compound fields (`BillingAddress`, `MailingAddress`, `Geolocation__c` with lat/long) cannot be used in `WHERE`. Filter on the individual component fields. They CAN appear in `SELECT` and projection.

---

## SQ-34 — `ORDER BY` and `GROUP BY` on Address / Geolocation compounds are also disallowed

```sql
SELECT Id FROM Account ORDER BY BillingAddress       -- MALFORMED
```

**Right**: order by the part you care about (`BillingState`, `BillingPostalCode`).

---

## SQ-35 — `DISTANCE()` function — Geolocation queries

**Right**
```sql
SELECT Id, Name FROM Account
WHERE DISTANCE(BillingAddress, GEOLOCATION(37.775,-122.418), 'mi') < 5
ORDER BY DISTANCE(BillingAddress, GEOLOCATION(37.775,-122.418), 'mi') LIMIT 100
```

**Rule**: `DISTANCE(...)` works in `WHERE` and `ORDER BY` against compound location fields. The unit string is `'mi'` or `'km'`. Repeating the call in `ORDER BY` is required — you cannot alias a `WHERE` distance and reuse it.

---

## SQ-36 — `SELECT` cannot use functions on most fields (Apex queries)

**Wrong**
```sql
SELECT UPPER(Name) FROM Account                      -- MALFORMED
```

**Right**: do the transformation in Apex after the query. SOQL doesn't have generic scalar functions. The narrow exceptions are aggregates (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `COUNT_DISTINCT`), `GROUPING(field)`, `FORMAT(field)`, `CALENDAR_*` date functions, `DAY_*`, `WEEK_*`, `FISCAL_*`, `convertCurrency()`, `convertTimezone()`, `DISTANCE()`, `GEOLOCATION()`.

---

## SQ-37 — `FORMAT(field)` returns localized strings — beware tests

**Right**
```sql
SELECT Id, FORMAT(AnnualRevenue) revFormatted FROM Account
```

**Rule**: `FORMAT()` applies the running user's locale — output is "$1,000.00" or "1.000,00 €" etc. Useful for display, dangerous for parsing. Tests that assert on the formatted string break when run under a user with a different locale. Use the typed field for assertions; `FORMAT()` only for human-facing output.

---

## SQ-38 — `WHERE` on `Type` fields uses `=`, not `IS`

**Wrong** (SQL-style):
```sql
SELECT Id FROM Account WHERE OwnerId IS NULL                      -- MALFORMED
```

**Right**:
```sql
SELECT Id FROM Account WHERE OwnerId = NULL
```

**Rule**: SOQL has no `IS NULL`/`IS NOT NULL`. Use `= NULL` and `!= NULL` (no quotes — see SQ-21).

---

## SQ-39 — `OR` between non-indexed fields kills selectivity

**Wrong** (perf):
```sql
SELECT Id FROM Account WHERE Name LIKE 'A%' OR Industry = 'Tech'   -- whole-table scan if neither is indexed
```

**Right** — split into two queries, or restructure:
```sql
-- Two narrow queries, merge in Apex
SELECT Id FROM Account WHERE Name LIKE 'A%' LIMIT 200
SELECT Id FROM Account WHERE Industry = 'Tech' LIMIT 200
```

**Rule**: `OR` requires both sides to be selective for the optimizer to use indexes; even one non-selective side disables index use across the whole `WHERE`. Prefer `AND` patterns; split disjunctions when the sides have different selectivity.

---

## SQ-40 — `SOSL` is not SOQL — different rules

```sql
FIND {Acme*} IN ALL FIELDS
RETURNING Account(Id, Name LIMIT 10), Contact(Id, FirstName, LastName LIMIT 10)
```

**Rule**: SOSL searches the search index across multiple objects. Indexes are eventually consistent — recently created records may not appear for ~15s. SOSL doesn't replace SOQL for known filters; use it specifically for full-text search. The `RETURNING` clause is mandatory if you want field projections.

---

## Quick checklist before sending SOQL for review

- [ ] No `SELECT *` (SQ-01)
- [ ] Date/datetime literals unquoted (SQ-03)
- [ ] Bind variables for every user input (no string concat) — see Apex AP-06
- [ ] Explicit `WITH USER_MODE` or documented `WITH SYSTEM_MODE` (SQ-14)
- [ ] No SOQL/DML in loops (SQ-32)
- [ ] No more than 5 levels of parent traversal (SQ-06)
- [ ] No nested subqueries (SQ-07)
- [ ] `ORDER BY` matches `SELECT` paths (SQ-22)
- [ ] `OFFSET ≤ 2000`; deep pagination uses keyset (SQ-17)
- [ ] `IN :coll` guarded against empty/oversized collections (SQ-31, SQ-04)
- [ ] Custom Metadata uses `getAll()/getInstance()`, not SOQL (SQ-19)
- [ ] Custom Settings use typed accessors, not SOQL (SQ-20)
- [ ] `LIKE` patterns avoid leading wildcards on large objects (SQ-02)
- [ ] No compound-field filters / orders (SQ-33, SQ-34)
- [ ] All aggregates aliased; non-aggregates in GROUP BY (SQ-08, SQ-09)
