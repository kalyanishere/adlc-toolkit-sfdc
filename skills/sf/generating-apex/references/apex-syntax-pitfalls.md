<!-- Parent: generating-apex/SKILL.md -->
# Apex Syntax & Runtime Pitfalls — what AI agents get wrong

A curated list of compile-time and runtime traps that AI code-generation agents most commonly produce when writing Apex. Each entry shows the wrong shape, the right shape, and the rule. Read this BEFORE authoring; cite an entry by ID (`AP-NN`) when reporting a fix.

Grounded in the [Apex Developer Guide](https://developer.salesforce.com/docs/atlas.en-us.apexcode.meta/apexcode/apex_dev_guide.htm). When in doubt, treat the official guide as the source of truth — these rules summarize what the guide enforces.

> Companion files: `salesforce-rules.md` (project rules), `partials/sf-quality-checklist.md` (always-on baseline). This file focuses on **language-mechanics** errors, not project policy.

---

## AP-01 — Sharing keyword on every top-level class

**Wrong**
```apex
public class AccountService { /* … */ }                  // implicit "without sharing"
```

**Right**
```apex
public with sharing class AccountService { /* … */ }
public without sharing class AdminBackfill { /* … */ }   // documented justification required
public inherited sharing class AccountSelector { /* … */ }
```

**Rule**: top-level classes that omit a sharing keyword run as the calling class's sharing OR `without sharing` in many contexts (anonymous Apex, system contexts). Always explicit. Inner classes inherit from the outer class — do not repeat the keyword on inner classes (it does nothing).

---

## AP-02 — Triggers cannot have a sharing keyword

**Wrong**
```apex
public with sharing trigger AccountTrigger on Account (before insert) { /* … */ }
```

**Right**
```apex
trigger AccountTrigger on Account (before insert, after insert, after update) {
    new AccountTriggerHandler().run();
}
```

**Rule**: triggers always run in system mode. Only the **handler class** can carry `with sharing` / `without sharing`. The trigger body itself takes no access modifier and no sharing keyword.

---

## AP-03 — Trigger context booleans are mutually exclusive in pairs

**Wrong**
```apex
trigger AccountTrigger on Account (before insert, before update, after insert, after update) {
    if (Trigger.isBefore && Trigger.isInsert) { /* before insert */ }
    if (Trigger.isAfter && Trigger.isUpdate) { /* after update */ }
    // Forgetting one event branch silently runs nothing for that event.
}
```

**Right** — handle all enumerated events explicitly, fail loud on unexpected:
```apex
if (Trigger.isBefore && Trigger.isInsert) { /* … */ }
else if (Trigger.isBefore && Trigger.isUpdate) { /* … */ }
else if (Trigger.isAfter && Trigger.isInsert)  { /* … */ }
else if (Trigger.isAfter && Trigger.isUpdate)  { /* … */ }
else { System.debug(LoggingLevel.WARN, 'Unhandled trigger context'); }
```

**Rule**: `Trigger.isBefore` / `isAfter` are mutually exclusive; `isInsert` / `isUpdate` / `isDelete` / `isUndelete` are mutually exclusive. Tests routinely fail when one branch is missing — list every event the trigger declares.

---

## AP-04 — `Trigger.new` is not modifiable in `after` triggers

**Wrong**
```apex
trigger AccountTrigger on Account (after insert) {
    for (Account a : Trigger.new) { a.Name = a.Name.toUpperCase(); }   // SObjectException
}
```

**Right**: do field mutations in `before` triggers; use `update` against fresh records in `after` triggers when you need post-insert IDs.

**Rule**: in `after` triggers, `Trigger.new` is read-only — assigning to a field throws `System.SObjectException`. Same for `Trigger.old` in any context, and `Trigger.new` in delete triggers (use `Trigger.old` instead).

---

## AP-05 — Don't reassign loop variables of `Trigger.new`

**Wrong**
```apex
for (Account a : Trigger.new) {
    a = new Account(Name='X');             // reassigning the iteration variable does nothing
}
```

**Right**
```apex
for (Account a : Trigger.new) {
    a.Name = 'X';                          // mutate fields in place (before triggers only)
}
```

**Rule**: assigning a new SObject to the loop variable does NOT replace the record in `Trigger.new` — Apex passes objects by reference but the variable is local. Mutate fields, do not reassign.

---

## AP-06 — Bind variables, not string concatenation, in dynamic SOQL

**Wrong**
```apex
String q = 'SELECT Id FROM Account WHERE Name = \'' + userInput + '\'';   // SOQL injection
List<Account> accts = Database.query(q);
```

**Right**
```apex
String name = userInput;                                // literal scope
List<Account> accts = Database.query(
    'SELECT Id FROM Account WHERE Name = :name'         // bind variable
);
// If concat is unavoidable for field/operator names, allowlist them via
// Schema.SObjectType.<X>.fields.getMap() and String.escapeSingleQuotes for values.
```

**Rule**: every user-controlled value in dynamic SOQL must be a bind variable (`:name`). For dynamic field/operator names that bind variables can't carry, use an allowlist from `Schema.describe`, never trust input.

---

## AP-07 — Database DML access level — explicit only

**Wrong**
```apex
insert accounts;                          // implicit AccessLevel — runs in current sharing context
Database.update(accounts, false);         // partial-success but no AccessLevel
```

**Right**
```apex
insert as user accounts;                                    // 60.0+ shorthand, USER_MODE
Database.insert(accounts, false, AccessLevel.USER_MODE);    // explicit, partial-success
List<Account> accts = [SELECT Id FROM Account WITH USER_MODE];
```

**Rule**: per `salesforce-rules.md`, every DML/SOQL statement must declare an explicit `AccessLevel`. `USER_MODE` enforces FLS + sharing. `SYSTEM_MODE` bypasses both — document why every time.

---

## AP-08 — `@future` is forbidden in new code

**Wrong**
```apex
@future public static void notifyExternal(Set<Id> accountIds) { /* callouts… */ }
```

**Right**
```apex
public class ExternalSyncQueueable implements Queueable, Database.AllowsCallouts {
    private final Set<Id> accountIds;
    public ExternalSyncQueueable(Set<Id> ids) { this.accountIds = ids; }
    public void execute(QueueableContext ctx) {
        System.attachFinalizer(new ExternalSyncFinalizer(accountIds));
        // … callouts here
    }
}
```

**Rule**: `@future` cannot chain, cannot be called from Batch, cannot accept SObject / non-primitive types beyond `Set<Id>`/`List<Id>`/primitives. Replace with Queueable + `System.Finalizer` for retry/cleanup. Project policy in `salesforce-rules.md` makes this a hard stop.

---

## AP-09 — `@AuraEnabled(cacheable=true)` requires read-only

**Wrong**
```apex
@AuraEnabled(cacheable=true)
public static void deleteAccounts(List<Id> ids) {
    delete [SELECT Id FROM Account WHERE Id IN :ids];   // throws AuraHandledException at runtime
}
```

**Right** — `cacheable=true` only on read-only:
```apex
@AuraEnabled(cacheable=true)
public static List<Account> getAccounts(Set<Id> ids) { /* SELECT only */ }

@AuraEnabled                                  // no cacheable on DML
public static void deleteAccounts(List<Id> ids) { /* DML */ }
```

**Rule**: `cacheable=true` mandates no DML, no callouts, no `Database.setSavepoint` — runtime detects mutation and throws. Use `cacheable=false` (or omit) for any DML / callout / setSavepoint method.

---

## AP-10 — `@AuraEnabled` exceptions must be `AuraHandledException`

**Wrong**
```apex
@AuraEnabled
public static void process(Id recordId) {
    if (recordId == null) throw new IllegalArgumentException('id required');   // exposes class name + message in LWC
}
```

**Right**
```apex
@AuraEnabled
public static void process(Id recordId) {
    try {
        if (recordId == null) throw new MyServiceException('Record ID is required');
        // …
    } catch (Exception e) {
        AuraHandledException ahe = new AuraHandledException(e.getMessage());
        ahe.setMessage(e.getMessage());            // setMessage required — see AP-10b
        throw ahe;
    }
}
```

**Rule**: any exception bubbling out of `@AuraEnabled` is wrapped by the platform as an opaque "Script-thrown exception" by default. To surface a useful message to the LWC, throw `AuraHandledException` AND call `setMessage(...)` on it — the constructor message is **not** what the client sees. (AP-10b)

---

## AP-11 — `Database.SaveResult` is required for partial-success DML

**Wrong**
```apex
Database.update(accts, false);                // result list silently ignored — bad records swallowed
```

**Right**
```apex
List<Database.SaveResult> results = Database.update(accts, false, AccessLevel.USER_MODE);
for (Integer i = 0; i < results.size(); i++) {
    if (!results[i].isSuccess()) {
        for (Database.Error err : results[i].getErrors()) {
            errorLogger.log(accts[i].Id, err.getStatusCode(), err.getMessage());
        }
    }
}
```

**Rule**: `Database.{insert|update|upsert|delete}(records, false)` returns a result list aligned 1:1 with the input. Always inspect `.isSuccess()` and `.getErrors()`; without that the partial-success flag is functionally a silent-fail.

---

## AP-12 — `addError()` only works in trigger / before-validation contexts

**Wrong**
```apex
public static void validate(List<Account> accts) {
    for (Account a : accts) {
        if (a.Name == null) a.addError('Name required');   // outside trigger context: no effect
    }
}
```

**Right** — call `addError()` only inside trigger handlers / before-trigger paths:
```apex
public static void validateInTrigger(List<Account> accts) {
    for (Account a : accts) {
        if (a.Name == null) a.addError('Name required');   // valid only when called from a before trigger
    }
}
```

**Rule**: `SObject.addError()` blocks the DML transaction — it is meaningful only during the trigger's pre-DML validation. From a service called outside a trigger, it does nothing visible. For pre-DML validation in services, throw a custom exception instead.

---

## AP-13 — Iterating `Trigger.newMap` of a delete trigger throws

**Wrong**
```apex
trigger AccountTrigger on Account (before delete) {
    for (Account a : Trigger.new) { /* runtime null-iter */ }
}
```

**Right**
```apex
trigger AccountTrigger on Account (before delete) {
    for (Account a : Trigger.old) { /* … */ }
}
```

**Rule**: `Trigger.new` and `Trigger.newMap` are `null` in delete triggers. `Trigger.old` and `Trigger.oldMap` are `null` in insert triggers. Use the right one for the context.

---

## AP-14 — `SOQL.size()` is the right governor counter; not `Limits.getQueryLocatorRows()` for non-batch

**Wrong**
```apex
if (Limits.getQueries() > 90) { /* hard-coded threshold, brittle */ }
```

**Right**
```apex
if (Limits.getQueries() >= Limits.getLimitQueries() - 10) { /* portable; relative to current limit */ }
```

**Rule**: never hard-code governor numbers (100, 150, 6 MB, etc.). The `Limits.getLimit*()` family is dynamic — it returns the right number per execution context (sync vs async vs batch). Hard-coded thresholds break the moment a method is called from a higher-limit context.

---

## AP-15 — `String` is not `Id`; `Id` is not `String`

**Wrong**
```apex
String accId = '001xx000003DGQ';
Account a = [SELECT Id FROM Account WHERE Id = :accId];   // works, but loses validation
List<Account> bad = [SELECT Id FROM Account WHERE Id = :userInput];   // unsafe shape
```

**Right**
```apex
Id accId = (Id) accId15Or18CharString;                    // throws StringException on bad shape
List<Account> accts = [SELECT Id FROM Account WHERE Id = :accId];
// For untrusted input:
if (!Pattern.matches('[a-zA-Z0-9]{15,18}', userInput)) throw new MyException('Invalid Id');
Id safe = (Id) userInput;
```

**Rule**: `Id` is its own primitive type with format validation. Casting via `(Id)` or assignment to an `Id` variable validates the shape; passing a raw `String` skips that. For any user-controlled record-id input, validate against the 15- or 18-char alphanumeric pattern before casting.

---

## AP-16 — `String.isBlank` vs `String.isEmpty` vs `== null`

**Wrong**
```apex
if (s == null || s.trim().length() == 0) { /* manual */ }
if (s.isEmpty()) { /* NPE if s is null */ }
```

**Right**
```apex
if (String.isBlank(s)) { /* null OR empty OR whitespace-only */ }
if (String.isEmpty(s)) { /* null OR empty (no whitespace check) */ }
```

**Rule**: `String.isBlank(s)` and `String.isEmpty(s)` are static, null-safe. Instance `s.isEmpty()` throws NPE if `s` is null. Default to `String.isBlank()` for "user provided meaningful input" checks.

---

## AP-17 — Map keys: SObject equality vs Id equality

**Wrong**
```apex
Map<Account, Decimal> totals = new Map<Account, Decimal>();
totals.put(account, 100);                                  // SObject equality — usually wrong
```

**Right**
```apex
Map<Id, Decimal> totals = new Map<Id, Decimal>();
totals.put(account.Id, 100);                               // Id equality
// Or if you must key by SObject, ensure stable identity (same instance) and document.
```

**Rule**: `Map<SObject, …>` uses SObject `equals/hashCode` which compares **all fields** of the SObject. Two queries returning the same record can have different field-sets and hash differently — silent map misses. Default to keying by `Id`.

---

## AP-18 — `Schema.SObjectType.<X>.fields.getMap()` keys are lowercase

**Wrong**
```apex
Schema.SObjectField f = Account.SObjectType.getDescribe().fields.getMap().get('Name');   // null
```

**Right**
```apex
Map<String, Schema.SObjectField> fieldMap = Account.SObjectType.getDescribe().fields.getMap();
Schema.SObjectField nameField = fieldMap.get('name');                       // lowercase key
// Or use the explicit token (preferred):
Schema.SObjectField nameField = Account.Name;
```

**Rule**: the field-map's keys are lower-cased API names. The map lookup with the camelCase API name returns null. Prefer `Account.<Field>` token references when the field name is known at compile time.

---

## AP-19 — Bulkified maps need `getRecordTypeInfosByDeveloperName()`, not `…ById()` for new code

**Wrong** — IDs differ per org, breaking deploys:
```apex
Id rtId = '012xx00000000XX';
```

**Right**
```apex
Id rtId = Account.SObjectType.getDescribe().getRecordTypeInfosByDeveloperName()
    .get('Customer').getRecordTypeId();
```

**Rule**: never hardcode a record-type ID. Use `getRecordTypeInfosByDeveloperName()` to look up the ID from the developer name (which is the same across orgs). Same applies to ProfileId, Permission Set Id, etc. — look them up by name at runtime.

---

## AP-20 — Casting `Object` to a typed list goes through `instanceof`

**Wrong**
```apex
Object raw = JSON.deserializeUntyped('[{"id":"a"},{"id":"b"}]');
List<Map<String,Object>> rows = (List<Map<String,Object>>) raw;        // runtime ClassCastException
```

**Right**
```apex
List<Object> raws = (List<Object>) JSON.deserializeUntyped(payload);
List<Map<String, Object>> rows = new List<Map<String, Object>>();
for (Object o : raws) rows.add((Map<String, Object>) o);
```

**Rule**: `JSON.deserializeUntyped()` returns `Object` typed as the loosest parent (`List<Object>` for arrays, `Map<String,Object>` for objects). You cannot cast `List<Object>` directly to `List<Map<String,Object>>` even when every element is one — Apex generics aren't covariant. Walk and cast per element, or use `JSON.deserialize(json, MyType.class)` with a typed Apex class.

---

## AP-21 — `JSON.deserialize` is case-sensitive on field names

**Wrong** — JSON has `"firstName"`, Apex has `String first_name;` → field stays null.

**Right** — match exactly, OR annotate:
```apex
public class Person {
    public String firstName;       // matches "firstName"
    public String last_name;       // matches "last_name" only — annotate if needed
}
```

**Rule**: `JSON.deserialize` matches by exact case. Mismatches silently produce null fields with no error. To rename, declare a typed wrapper class with `@JsonAccess` or use `JSON.deserializeUntyped` and translate manually.

---

## AP-22 — Static variables are transaction-scoped, not request-scoped

**Wrong** assumption:
```apex
public class Cache {
    public static Map<Id, Account> cache = new Map<Id, Account>();   // shared across requests? No.
}
```

**Right**:
```apex
// Static is reset between top-level Apex invocations (transactions). Use Cache.Org / Cache.Session
// for cross-transaction caching; static maps for in-transaction memoization only.
```

**Rule**: `static` in Apex means "transaction-scoped" — a new value at the start of every request. They do persist across method calls inside a single trigger handler / Visualforce action. Use `Cache.Org` / `Cache.Session` for cross-transaction state; never rely on `static` for it.

---

## AP-23 — Apex string concat of nulls produces `"null"`, not throws

**Wrong**
```apex
String greeting = 'Hello ' + user.Name;   // if Name is null → "Hello null"
```

**Right**
```apex
String greeting = 'Hello ' + (user.Name == null ? '' : user.Name);
// Or, 60.0+:
String greeting = 'Hello ' + (user.Name ?? '');
```

**Rule**: Apex `+` on a null operand produces the literal string `"null"`. Use safe-coalesce (`??` on 60.0+) or explicit null-check.

---

## AP-24 — `List.contains()` is O(n); use `Set.contains()` for membership

**Wrong**
```apex
List<Id> watch = …;
for (Account a : accounts) {
    if (watch.contains(a.Id)) { /* O(watch.size()) per record — quadratic */ }
}
```

**Right**
```apex
Set<Id> watch = new Set<Id>(rawWatchList);
for (Account a : accounts) {
    if (watch.contains(a.Id)) { /* O(1) */ }
}
```

**Rule**: `List.contains()` linearly scans. Convert to `Set` once when used inside a loop or when list size > 10. Same for `Set.removeAll(otherSet)` vs equivalent loop.

---

## AP-25 — Don't call `Database.executeBatch()` from a trigger

**Wrong**
```apex
trigger AccountTrigger on Account (after update) {
    Database.executeBatch(new MyBatch(), 200);   // System.AsyncException at scale
}
```

**Right** — chain via Queueable from the trigger, then enqueue Batch from the Queueable when truly needed.

**Rule**: Salesforce limits async invocations from a single transaction (50 jobs total, mix of queueable/batch/future). Triggers fire in bulk (200-record chunks); calling `executeBatch` on every chunk explodes. Defer to Queueable with state, or accumulate IDs and enqueue once.

---

## AP-26 — `Test.startTest()` resets governor limits — use it once

**Wrong**
```apex
@isTest static void test() {
    Test.startTest();
    methodA();
    Test.stopTest();
    Test.startTest();          // System.AssertException — startTest can be called only once
    methodB();
    Test.stopTest();
}
```

**Right**: one `startTest/stopTest` block per test method, around the unit under test.

**Rule**: `Test.startTest()` may be called once per test method. The block grants a fresh governor pool AND forces async jobs (Queueable, Batch, scheduled) to complete synchronously by `Test.stopTest()`. Wrap only the code under test, not the setup.

---

## AP-27 — `final` doesn't make collections immutable

**Wrong**
```apex
public final List<String> tags = new List<String>{ 'a', 'b' };
tags.add('c');                                        // works — final only blocks reassignment
```

**Right** — if you need true immutability, expose only via a getter that returns a copy or use a wrapper.

**Rule**: `final` prevents reassignment of the variable. The collection's contents are still mutable. Document carefully when exposing collections via `public final`.

---

## AP-28 — `system.runAs()` is the only way to test sharing/CRUD/FLS

**Wrong**
```apex
@isTest static void testAsAdmin() {
    insert new Account(Name='Foo');                  // runs as the test runner — admin equivalent
    Test.startTest();
    AccountService.scrub();
    Test.stopTest();
    // claims FLS coverage but actually ran as admin
}
```

**Right**
```apex
User u = [SELECT Id FROM User WHERE Profile.Name = 'Standard User' AND IsActive = true LIMIT 1];
System.runAs(u) {
    Test.startTest();
    AccountService.scrub();
    Test.stopTest();
}
```

**Rule**: tests run as the `Automated Process` system user by default — sharing rules, CRUD, and FLS are bypassed. Only `System.runAs(user) { … }` enforces them. Any test claiming to cover sharing/FLS that doesn't `runAs` is misleading.

---

## AP-29 — `System.assertEquals` is deprecated; use `Assert.areEqual`

**Wrong**
```apex
System.assertEquals(expected, actual);                // legacy; works but deprecated
```

**Right** (API 60.0+):
```apex
Assert.areEqual(expected, actual, 'message describing what the assertion is checking');
Assert.isTrue(condition, 'why this should be true');
Assert.isInstanceOfType(value, MyClass.class);
Assert.fail('reached unreachable branch');
```

**Rule**: the `Assert` class is the modern API; provides better error messages and richer assertion shapes. Any new test should use it.

---

## AP-30 — Callouts forbidden after DML in same transaction (without async marker)

**Wrong**
```apex
public static void process(Id recordId) {
    insert new Log__c(Message__c='start');           // DML
    HttpResponse res = http.send(req);               // System.CalloutException: You have uncommitted work pending
}
```

**Right** — order callout BEFORE any DML, or move DML to a Queueable/future:
```apex
public static void process(Id recordId) {
    HttpResponse res = http.send(req);              // callout first
    insert new Log__c(Message__c='done');           // DML after
}
```

**Rule**: Salesforce forbids callouts after DML in the same transaction (uncommitted-work guard). Workarounds: do all callouts before any DML, or move the DML+callout pair into Queueable/`@future(callout=true)` (legacy — prefer Queueable + `Database.AllowsCallouts`).

---

## AP-31 — `Set<SObject>` is allowed but rarely useful

**Wrong**
```apex
Set<Account> uniqueAccounts = new Set<Account>(accountList);   // dedup by SObject equals — all-fields
```

**Right**
```apex
Map<Id, Account> uniqueById = new Map<Id, Account>(accountList);  // dedup by Id (typical intent)
```

**Rule**: `Set<SObject>` deduplicates by `equals/hashCode` over all populated fields. Two query rows for the same record will likely both end up in the set. The `Map<Id, SObject>` constructor over a list is the deduplicate-by-Id idiom.

---

## AP-32 — `@TestVisible` is required for tests to call `private` members

**Wrong** — test sees `private static void compute()` → compile fails.

**Right**
```apex
@TestVisible
private static void compute() { /* … */ }                   // tests can call this; production code can't
```

**Rule**: `@TestVisible` widens visibility only for the test runtime. Use it sparingly — preferably refactor to test through public APIs first. But never make a method public solely to test it.

---

## AP-33 — `Schema.DescribeFieldResult.isAccessible()` ≠ `isCreateable()` ≠ `isUpdateable()`

**Wrong** — using `isAccessible` to gate writes:
```apex
if (Account.SObjectType.getDescribe().fields.getMap().get('name').getDescribe().isAccessible()) {
    update accts;                                   // wrong — accessible covers READ only
}
```

**Right**
```apex
DescribeFieldResult dfr = Account.Name.getDescribe();
if (dfr.isUpdateable()) { /* allow update */ }
if (dfr.isCreateable()) { /* allow insert */ }
if (dfr.isAccessible()) { /* allow read */ }
```

**Rule**: `isAccessible` = read FLS, `isCreateable` = create FLS, `isUpdateable` = update FLS. They are independent — using the wrong one gates the wrong operation.

---

## AP-34 — Soft governor limits in async are higher, but not unlimited

**Soft assumption** — "Batch is infinite" is wrong:
| Context | SOQL queries | DML | Heap | CPU |
|---|---|---|---|---|
| Synchronous Apex (default) | 100 | 150 | 6 MB | 10,000 ms |
| `@future` / Queueable / Batch.execute / Schedulable | 200 | 150 | 12 MB | 60,000 ms |
| Batch.start (QueryLocator) | 5 (15M rows) | n/a | 12 MB | 60,000 ms |

Use `Limits.getLimit*()` to read the actual current ceiling — never hard-code these numbers.

---

## AP-35 — Catching `Exception` swallows `LimitException` (do not catch governor failures)

**Wrong**
```apex
try { /* big work */ }
catch (Exception e) { logger.log(e); }    // also catches System.LimitException — swallows governor failure
```

**Right**
```apex
try { /* big work */ }
catch (DmlException e)     { /* domain handling */ }
catch (CalloutException e) { /* domain handling */ }
catch (Exception e) {
    if (e instanceof System.LimitException) throw e;     // do NOT swallow
    logger.log(e);
    throw e;
}
```

**Rule**: `System.LimitException` (governor breach) is uncatchable in the sense that **catching and swallowing it is forbidden** — the platform re-throws it after the catch block. Best practice: either don't catch generic `Exception`, or rethrow `LimitException` explicitly.

---

## AP-36 — `Savepoint` rollback discards all DML, including triggers, since the savepoint

**Wrong** — assuming partial rollback:
```apex
Savepoint sp = Database.setSavepoint();
insert acc;
insert con;             // fails
Database.rollback(sp);  // rolls back BOTH inserts — and any trigger-side-effect DML in between
```

**Right**: design transactions so a savepoint rollback restores a **clean** state. Don't fire callouts between the savepoint and the rollback (Salesforce blocks that anyway).

**Rule**: a `Savepoint` rollback unwinds all DML (including trigger-side-effects) since the savepoint. Useful for "all-or-nothing" mid-transaction patches; not a partial-undo tool.

---

## AP-37 — `String.escapeSingleQuotes` is not enough on its own

**Wrong** — relying on escape only for dynamic SOQL:
```apex
String q = 'SELECT Id FROM Account WHERE Name LIKE \'%' + String.escapeSingleQuotes(input) + '%\'';
```

This still allows `'` in the input to be escaped as `\'` and then SOQL-injected via control characters in some edge paths.

**Right**: always prefer bind variables. Use `escapeSingleQuotes` as defense-in-depth only when bind isn't possible (e.g. dynamic field name path, but even there allowlist via `Schema.describe`).

**Rule**: bind > allowlist > escape. Never escape-only.

---

## AP-38 — `getDescribe()` is expensive — cache it

**Wrong** — every method describes:
```apex
Schema.SObjectType.Account.getDescribe();   // CPU + heap each call
```

**Right** — describe once at static init:
```apex
private static final Schema.DescribeSObjectResult ACCOUNT_DESCRIBE = Account.SObjectType.getDescribe();
```

**Rule**: `getDescribe()` (object and field forms) is a measurable hot path. Hoist to `static final` constants. Same for `getRecordTypeInfosByDeveloperName()`.

---

## AP-39 — `LimitException` from `Limits.getLimit*` itself is impossible

The `Limits.*` accessors do NOT consume any governor budget — they cannot fail. Use them freely. Don't wrap them in a try/catch "to be safe"; that's noise.

---

## AP-40 — Unit-test classes & methods need `@isTest` (capital I optional but stylized)

**Wrong**
```apex
public class MyTest {
    static testMethod void shouldDoFoo() { /* legacy syntax — works but deprecated */ }
}
```

**Right**
```apex
@IsTest
private class MyTest {
    @IsTest
    static void shouldDoFoo() { /* … */ }
}
```

**Rule**: `@IsTest` is the modern annotation. The legacy `testMethod` keyword still compiles but is deprecated. Test classes themselves should be `@IsTest` (excluded from coverage and from production class limits) and `private` (test classes never need to be `public`).

---

## Quick checklist before sending Apex for review

- [ ] Sharing keyword on every top-level class (AP-01)
- [ ] No `@future`; Queueable + Finalizer instead (AP-08)
- [ ] Explicit `AccessLevel` on every SOQL/DML; default USER_MODE (AP-07)
- [ ] All dynamic SOQL uses bind variables (AP-06, AP-37)
- [ ] No SOQL/DML in loops; partial-success DML inspects `SaveResult` (AP-11)
- [ ] `cacheable=true` only on read-only `@AuraEnabled` (AP-09)
- [ ] `@AuraEnabled` exceptions wrapped as `AuraHandledException` with `setMessage` (AP-10)
- [ ] No hard-coded governor numbers; use `Limits.getLimit*()` (AP-14)
- [ ] No hard-coded record-type / profile / app IDs; lookup by developer name (AP-19)
- [ ] No swallowing `LimitException` (AP-35)
- [ ] `Test.startTest/stopTest` once per method, around unit under test (AP-26)
- [ ] `Assert.*` (not deprecated `System.assertEquals`) (AP-29)
- [ ] `System.runAs` for any test claiming sharing/FLS coverage (AP-28)
