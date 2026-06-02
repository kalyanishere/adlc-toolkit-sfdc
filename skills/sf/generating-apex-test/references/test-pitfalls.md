<!-- Parent: generating-apex-test/SKILL.md -->
# Apex Test Syntax & Runtime Pitfalls — what AI agents get wrong

A targeted catalog of test-only traps that produce compile-time errors, false-positive coverage, or runtime "no data" failures. Each entry shows the wrong shape, the right shape, and the rule.

Grounded in the [Apex Developer Guide → Testing](https://developer.salesforce.com/docs/atlas.en-us.apexcode.meta/apexcode/apex_testing.htm). When in doubt, treat the official guide as authoritative.

> Companion files: `assertion-patterns.md`, `async-testing.md`, `mocking-patterns.md`, `test-data-factory.md`. This file focuses on **language-mechanics** errors specifically — not test-design quality.

---

## TP-01 — `@isTest` on the class makes it private; tests don't go in production classes

**Wrong**
```apex
public class AccountServiceTest {                       // counts toward production class limit; tests in prod code
    public static testMethod void testFoo() { /* legacy */ }
}
```

**Right**
```apex
@IsTest
private class AccountServiceTest {
    @IsTest
    static void shouldReturnZeroWhenNoAccounts() { /* … */ }
}
```

**Rule**: test classes MUST be `@IsTest` (excludes from coverage; doesn't count against organization Apex character limit) and `private` (test classes never need to be public). The legacy `testMethod` keyword still compiles but is deprecated — use `@IsTest` on each method.

---

## TP-02 — `@TestSetup` runs once per class; data persists across test methods

**Wrong** assumption — `@TestSetup` runs before every method:
```apex
@IsTest private class AccountTest {
    @TestSetup static void setup() { insert new Account(Name='S1'); }

    @IsTest static void testA() {
        update [SELECT Id FROM Account];                // mutates the shared row
    }
    @IsTest static void testB() {
        Account a = [SELECT Name FROM Account];          // sees mutation? No — rolled back.
    }
}
```

**Right** — understand the boundary:
```apex
// @TestSetup data is inserted once, then the platform takes a savepoint.
// Each @IsTest method runs against that savepoint and rolls back at exit.
// So tests CANNOT see each other's mutations to setup data; they always see the original setup state.
```

**Rule**: `@TestSetup` runs once per test class. Each individual test method runs in its own implicit savepoint — DML in test methods is rolled back at method end. Mutations from one method are not visible to another. This is automatic isolation; do not implement your own.

---

## TP-03 — `@TestSetup` cannot reference itself or instance state

**Wrong**
```apex
@IsTest private class AccountTest {
    static Integer counter = 0;
    @TestSetup static void setup() { counter++; }       // counter resets each method anyway
    @IsTest static void test() {
        Assert.areEqual(1, counter);                     // FAIL — counter is 0 here, not 1
    }
}
```

**Rule**: `@TestSetup` runs in its own transaction. Static variables modified inside `@TestSetup` are NOT visible to test methods — those methods start with fresh static state. Pass needed values via querying the data created by setup, not via static variables.

---

## TP-04 — `Test.startTest() / Test.stopTest()` resets governor limits exactly once

**Wrong**
```apex
@IsTest static void test() {
    Test.startTest();
    methodA();
    Test.stopTest();
    Test.startTest();           // System.AssertException — already stopped
    methodB();
    Test.stopTest();
}
```

**Right** — one `startTest/stopTest` block per method, around the unit under test:
```apex
@IsTest static void shouldProcessFooBar() {
    // setup work — uses default governor pool
    List<Account> accts = TestDataFactory.makeAccounts(10);
    insert accts;

    Test.startTest();           // fresh governor pool starts here
    AccountService.process(accts);
    Test.stopTest();            // forces async (Queueable/Batch) to drain

    // assertions
}
```

**Rule**: `Test.startTest()` may be called once per test method. The block grants a fresh governor pool AND forces queued async (Queueable, Batch, scheduled) to complete by `Test.stopTest()`. Wrap only the call under test, not setup or assertion code.

---

## TP-05 — Async tests need `Test.stopTest()` for the async to actually run

**Wrong**
```apex
@IsTest static void testQueueable() {
    Test.startTest();
    System.enqueueJob(new MyQueueable());
    // missing Test.stopTest()
    Account a = [SELECT Status__c FROM Account WHERE Id=:rec.Id];
    Assert.areEqual('Done', a.Status__c);                // FAIL — Queueable hasn't executed
}
```

**Right**
```apex
@IsTest static void testQueueable() {
    Account rec = TestDataFactory.makeAccount();
    insert rec;
    Test.startTest();
    System.enqueueJob(new MyQueueable(rec.Id));
    Test.stopTest();                                      // <-- Queueable runs synchronously here
    Account a = [SELECT Status__c FROM Account WHERE Id=:rec.Id];
    Assert.areEqual('Done', a.Status__c);
}
```

**Rule**: in test context, async jobs queued inside the start/stop block run synchronously when `stopTest()` returns. Without `stopTest()`, the async never runs and the assertion sees pre-async state. Same applies to `Database.executeBatch()`, `System.schedule()`, `@future`.

---

## TP-06 — `System.runAs` is the only way to test sharing/CRUD/FLS

**Wrong**
```apex
@IsTest static void testReadOnlyUserSeesNothing() {
    insert new Account(Name='Confidential');
    AccountService.scrub();                              // runs as test runner — full admin access
    // claims FLS / sharing coverage — actually doesn't have any
}
```

**Right**
```apex
@IsTest static void testReadOnlyUserSeesNothing() {
    User u = [SELECT Id FROM User WHERE Profile.Name='Read Only' AND IsActive=true LIMIT 1];
    Account a = new Account(Name='Confidential');
    insert a;

    System.runAs(u) {
        Test.startTest();
        List<Account> seen = AccountService.findAll();
        Test.stopTest();
        Assert.areEqual(0, seen.size());
    }
}
```

**Rule**: tests run as the system "Automated Process" user — sharing rules, CRUD, and FLS are bypassed. Only `System.runAs(user) { … }` enforces them. Any test claiming FLS/sharing coverage that doesn't `runAs` is misleading and provides false confidence.

---

## TP-07 — `runAs` blocks DML governor limits but NOT mixed-DML rules

**Wrong**
```apex
@IsTest static void testMixedDml() {
    User u = [SELECT Id FROM User LIMIT 1];
    System.runAs(u) {
        insert new User(Username='x@y.com.test', /* … */);     // setup DML on User
        insert new Account(Name='A');                          // non-setup DML — MIXED_DML_OPERATION
    }
}
```

**Right** — separate setup and non-setup DML; do User/Group/Profile/Permission* DML in its own `runAs` block, away from object DML:
```apex
User u;
System.runAs(new User(Id=UserInfo.getUserId())) {
    u = new User(Username='x@y.com.test', /* … */);
    insert u;
}
System.runAs(u) {
    insert new Account(Name='A');
}
```

**Rule**: tests cannot mix DML on "setup objects" (User, Profile, PermissionSet, Group, GroupMember, RecordType, etc.) with DML on regular objects in the same transaction. The platform throws `MIXED_DML_OPERATION`. The fix is to do the setup DML inside an outer `runAs(currentUser)` block before the test body.

---

## TP-08 — `@isTest(SeeAllData=true)` is forbidden

**Wrong**
```apex
@IsTest(SeeAllData=true)
private class BadTest { /* — banned by salesforce-rules.md */ }
```

**Right** — create your own data via `@TestSetup` + a `TestDataFactory`:
```apex
@IsTest private class GoodTest {
    @TestSetup static void setup() {
        TestDataFactory.makeAccounts(10);
    }
    @IsTest static void test() { /* … */ }
}
```

**Rule**: `SeeAllData=true` means the test sees the org's existing data. Tests become non-deterministic, break across orgs, and silently rely on data that may not exist later. Project rule (`salesforce-rules.md`) bans it; one of the very few platform features whose use is a Critical finding.

---

## TP-09 — `@TestVisible` widens visibility ONLY for tests

**Wrong** — exposing helper to test:
```apex
public class AccountService {
    public static void compute(Account a) { /* internal helper exposed for tests */ }
}
```

**Right**
```apex
public class AccountService {
    @TestVisible
    private static void compute(Account a) { /* … */ }     // tests can call; production cannot
}
```

**Rule**: `@TestVisible` allows test-only access to private/protected members. Don't make members `public` solely for testability — that pollutes the public surface. Note: `@TestVisible` works on fields, methods, and inner classes.

---

## TP-10 — `Test.setMock(HttpCalloutMock.class, mock)` MUST be called before the callout

**Wrong**
```apex
@IsTest static void test() {
    HttpResponse res = MyService.fetch();                 // real callout attempt — fails
    Test.setMock(HttpCalloutMock.class, new MyMock());    // too late
}
```

**Right**
```apex
@IsTest static void test() {
    Test.setMock(HttpCalloutMock.class, new MyMock());    // register first
    Test.startTest();
    HttpResponse res = MyService.fetch();                  // intercepted by mock
    Test.stopTest();
}
```

**Rule**: callout mocks must be registered before the call that triggers the callout. Same for `WebServiceMock`. Mocks installed after the call have no effect, and the real callout fails because tests cannot make real HTTP calls.

---

## TP-11 — Tests cannot make real HTTP callouts; cannot send email; cannot enqueue scheduled jobs that already exist

**Rules**:
- **HTTP callouts in tests** must be mocked (`Test.setMock(HttpCalloutMock.class, ...)`) or wrapped in `Test.isRunningTest()` short-circuits.
- **`Messaging.sendEmail`** in tests does not actually send; the platform records it for `Limits.getEmailInvocations()`.
- **`System.schedule(name, …)`**: name conflicts with an existing scheduled job throw — use a unique test-time name (`'TEST_' + Math.random()` is safe in tests where the date functions are stubbable).
- **`Test.isRunningTest()`** is the canonical "skip in test" check; better than feature flags.

---

## TP-12 — `@IsTest(IsParallel=true)` opts in to running outside the test queue

**Right**
```apex
@IsTest(IsParallel=true)
private class IsolatedAccountTest {
    /* methods can run concurrently with other parallel-marked tests */
}
```

**Rule**: by default Apex tests run serially. `IsParallel=true` lets the runner parallelize this class with other parallel-marked classes — speeds up large test suites. Forbidden when the test mutates shared state (User records, custom settings, scheduled jobs). Default OFF; opt in only for read-mostly tests.

---

## TP-13 — `Test.loadData(StaticResource, csvName)` requires a static resource — not a path

**Wrong**
```apex
List<sObject> rows = Test.loadData(Account.sObjectType, 'force-app/main/default/staticresources/Accounts.csv');
```

**Right**
```apex
// 1. Upload Accounts.resource (zipped CSV) as a StaticResource
// 2. Call by static-resource name (no extension):
List<sObject> rows = Test.loadData(Account.sObjectType, 'TestAccounts');
```

**Rule**: `Test.loadData` reads a CSV from a deployed `StaticResource`, not a filesystem path. The static resource name is the developer name, no `.resource` suffix. Useful for large fixtures; otherwise prefer a `TestDataFactory` for clarity.

---

## TP-14 — Test classes cannot use `@future` to create test data

**Wrong**
```apex
@IsTest static void test() {
    DataLoader.loadAsync();                              // contains @future — System.AsyncException in test
}
```

**Right** — the `@future` body runs during `Test.stopTest()`. Inspect post-stop:
```apex
@IsTest static void test() {
    Test.startTest();
    DataLoader.loadAsync();
    Test.stopTest();
    // @future has now executed; assert state.
}
```

**Rule**: same as Queueable/Batch — async runs at `stopTest`. Tests CAN call `@future` methods (they just run synchronously at stopTest). What they cannot do is verify state mid-async; assertions must be post-stop.

---

## TP-15 — `@TestSetup` cannot itself enqueue async jobs that will affect later tests

**Wrong**
```apex
@TestSetup static void setup() {
    System.enqueueJob(new ImportQueueable());            // queued, not run
    // The Queueable does NOT execute before test methods run — it never runs in test context
    // unless wrapped in Test.startTest/stopTest, which @TestSetup can't usefully do.
}
```

**Rule**: async work queued in `@TestSetup` does not run before the test methods. Use `@TestSetup` for synchronous DML only. If you need post-async state, do the async + `stopTest()` inside the test method.

---

## TP-16 — `Database.QueryLocator` in `start()` is exempt from the 50K-row limit

```apex
public Database.QueryLocator start(Database.BatchableContext bc) {
    return Database.getQueryLocator('SELECT Id FROM Account');   // can return 50M rows
}
```

**Rule**: in a Batch's `start()`, `Database.QueryLocator` is the right pattern for full-table scans. The returned locator is iterated lazily — `start()` itself doesn't materialize the rows. Tests that exercise Batch should use a small mock dataset; the locator's row count in test is bounded only by your `@TestSetup` data.

---

## TP-17 — Coverage counts test-method *line execution*, not test *quality*

**Wrong** — `Assert.areEqual(true, true)` for coverage:
```apex
@IsTest static void coverIt() {
    AccountService.process(new Account(Name='X'));
    Assert.areEqual(true, true);                         // 100% line coverage, 0% verification
}
```

**Right** — assert observable behavior:
```apex
@IsTest static void shouldNormalizeNameOnInsert() {
    Account a = new Account(Name='  Acme  ');
    AccountService.normalizeAndSave(new List<Account>{ a });
    Account stored = [SELECT Name FROM Account WHERE Id=:a.Id];
    Assert.areEqual('Acme', stored.Name, 'expected trimmed name');
}
```

**Rule**: project policy mandates *meaningful* assertions — coverage without assertions is a Critical finding from the test-auditor (REQ-A coverage policy). Per `salesforce-rules.md`, vacuous tests fail review.

---

## TP-18 — `System.assert*` is deprecated; use `Assert.*`

**Wrong**
```apex
System.assertEquals(2, total);
System.assert(condition);
System.assertNotEquals(null, result);
```

**Right** (60.0+):
```apex
Assert.areEqual(2, total, 'expected 2 totals after grouping');
Assert.isTrue(condition, 'expected condition to hold because …');
Assert.isNotNull(result, 'service should never return null');
Assert.fail('reached unreachable branch in switch');
Assert.isInstanceOfType(result, AccountService.Response.class);
```

**Rule**: the `Assert` class is the modern API — better error messages, richer assertions. New tests must use it.

---

## TP-19 — Multi-method coverage requires uncovering of governor branches

**Wrong**
```apex
@IsTest static void test() {
    AccountService.process(makeAccounts(1));             // happy path only
}
```

**Right** — exercise edge branches:
```apex
@IsTest static void shouldHandleEmptyInput() { AccountService.process(new List<Account>()); }
@IsTest static void shouldHandleSingleRecord() { AccountService.process(makeAccounts(1)); }
@IsTest static void shouldHandleBulkLoad() { AccountService.process(makeAccounts(200)); }   // bulk
@IsTest static void shouldRejectInvalid() {
    try { AccountService.process(null); Assert.fail('expected null guard'); }
    catch (IllegalArgumentException e) { /* expected */ }
}
```

**Rule**: every public method should have at least: happy path, empty/null input, bulk path (200 records — same governor budget as a real trigger), and explicitly-tested error path with `Assert.fail` if the throw doesn't happen. Single-method coverage that only hits the happy path is a Major finding.

---

## TP-20 — `UserInfo.getUserId()` in tests returns the test runner's id

**Right** when relying on it:
```apex
Account a = new Account(Name='X', OwnerId = UserInfo.getUserId());
insert a;
```

**Rule**: in tests, `UserInfo.getUserId()` returns the user that's running the test (default: the test runner). Inside `System.runAs(otherUser)`, it returns `otherUser.Id`. Keep this in mind when asserting ownership.

---

## TP-21 — Test methods cannot return values

**Wrong**
```apex
@IsTest static Integer countSomething() { return 1; }   // compile error
```

**Right**
```apex
@IsTest static void shouldCountCorrectly() {
    Integer actual = AccountService.count();
    Assert.areEqual(1, actual);
}
```

**Rule**: `@IsTest` methods must be `void` and take no parameters. Each is its own test entry point. Helpers can be `private static` non-`@IsTest` methods within the test class.

---

## TP-22 — Test methods can throw, but the runner reports it as failed

**Right** — when verifying that production code throws:
```apex
@IsTest static void shouldThrowOnNullInput() {
    try {
        AccountService.process(null);
        Assert.fail('expected MyException for null input');
    } catch (MyException e) {
        Assert.areEqual('Input required', e.getMessage());
    }
}
```

**Rule**: an uncaught exception in a test method = test failure. Use try/catch + `Assert.fail` to verify expected exceptions. Do not annotate with anything Java-like — Apex has no `@Test(expected=…)`.

---

## TP-23 — `Test.invokeContinuationMethod` is the only way to test Continuations

```apex
@IsTest static void testContinuation() {
    Test.startTest();
    Continuation c = (Continuation) MyController.startCallout();
    Test.setContinuationResponse(c.getRequestLabel(), new HttpResponse(/*…*/));
    Object res = Test.invokeContinuationMethod(new MyController(), c);
    Test.stopTest();
}
```

**Rule**: Continuation callbacks aren't reachable via plain method calls in tests. Use `Test.setContinuationResponse` + `Test.invokeContinuationMethod` to simulate the long-running response. Without these, the callback never runs and coverage stays at the entry method.

---

## TP-24 — `Test.enqueueJob` does NOT exist; use `System.enqueueJob` and rely on stopTest

**Wrong**
```apex
Test.enqueueJob(new MyQueueable());                     // compile error
```

**Right**
```apex
Test.startTest();
Id jobId = System.enqueueJob(new MyQueueable());
Test.stopTest();    // job runs here in test context
```

(Trivial-looking but a common AI hallucination — `Test.foo` patterns get over-generalized.)

---

## TP-25 — `@SeeAllData=false` is the default — say so explicitly only when overriding within a class

**Right** — class-level setup excludes data, but a single method can opt-in (still discouraged):
```apex
@IsTest private class MyTest {
    @IsTest static void normalTest() { /* SeeAllData=false (default) */ }

    @IsTest(SeeAllData=true)                            // opts THIS method in only — still avoid
    static void onlyIfYouMust() { /* … */ }
}
```

**Rule**: omit `SeeAllData=false` — it's the default. Per project rule `SeeAllData=true` is banned everywhere, including method-level (TP-08).

---

## TP-26 — `Limits.getQueries()` in tests starts fresh per method (and again at startTest)

**Right**
```apex
@IsTest static void test() {
    Test.startTest();                                    // resets governor counters here
    methodUnderTest();
    System.debug('queries used: ' + Limits.getQueries());
    Test.stopTest();
}
```

**Rule**: each test method gets its own governor pool (200 SOQL queries in test contexts vs 100 sync). `Test.startTest()` resets again — so the call under test gets a completely fresh budget. Useful for asserting governor consumption: `Assert.isTrue(Limits.getQueries() < 5, '…')`.

---

## TP-27 — `Test.createStub(MockClass.class, instance)` for Apex-class mocking (Stub API)

**Right**
```apex
@IsTest static void test() {
    AccountSelector mockSelector = (AccountSelector) Test.createStub(
        AccountSelector.class, new AccountSelectorMock()
    );
    AccountService svc = new AccountService(mockSelector);
    // svc methods that call mockSelector use the stub instead of real
}
// where AccountSelectorMock implements System.StubProvider
```

**Rule**: the Stub API lets you mock concrete Apex classes without rewriting the production class to use interfaces. Class being stubbed must be `virtual`, `abstract`, or marked `@TestVisible` for non-virtual. The mock implements `System.StubProvider`'s `handleMethodCall(...)`. Dependency injection (constructor params) is still cleaner — use the Stub API only when you can't refactor.

---

## TP-28 — `@RestResource` test pattern — set RestRequest, invoke directly

**Right**
```apex
@IsTest static void testRestEndpoint() {
    RestRequest req = new RestRequest();
    req.requestUri = '/services/apexrest/Account/v1/123';
    req.httpMethod = 'GET';
    RestContext.request = req;
    RestContext.response = new RestResponse();

    Test.startTest();
    AccountRestResource.doGet();
    Test.stopTest();

    Assert.areEqual(200, RestContext.response.statusCode);
}
```

**Rule**: REST resource methods read from and write to `RestContext`. In tests, set `RestContext.request` and `RestContext.response` manually before invoking the method. There is no built-in HTTP server.

---

## TP-29 — Default org-data assumptions break tests across orgs

**Wrong**
```apex
@IsTest static void test() {
    User u = [SELECT Id FROM User WHERE FirstName='Admin' LIMIT 1];   // assumes org has this user
}
```

**Right**
```apex
@IsTest static void test() {
    User u = [SELECT Id FROM User WHERE Profile.Name='System Administrator' AND IsActive=true LIMIT 1];
    // Or even better — create a test User in @TestSetup if your test mutates state
}
```

**Rule**: never rely on data that varies across orgs. Profile names are stable enough; user names, account names, custom-setting defaults are not. Default to creating fresh data via `TestDataFactory`.

---

## TP-30 — `@IsTest static List<…> setupX()` helper in same test class is fine — but not annotated

**Right**
```apex
@IsTest private class MyTest {
    // helper, NOT @IsTest — just a private static method in a @IsTest class
    private static List<Account> makeAccounts(Integer n) {
        List<Account> out = new List<Account>();
        for (Integer i = 0; i < n; i++) out.add(new Account(Name='A'+i));
        return out;
    }

    @IsTest static void shouldFoo() {
        List<Account> as = makeAccounts(3);
        insert as;
        // …
    }
}
```

**Rule**: helpers in a `@IsTest` class don't need `@IsTest` themselves — they're only callable from test code (the class is private). The annotation excludes helpers from coverage but also from being entry points.

---

## Quick checklist before sending tests for review

- [ ] `@IsTest` on class AND every test method (TP-01)
- [ ] Class is `private` (TP-01)
- [ ] No `SeeAllData=true` (TP-08, TP-25)
- [ ] `@TestSetup` for shared data; understand it runs once + savepoint isolates methods (TP-02)
- [ ] `Test.startTest()/stopTest()` once per method, around the unit under test (TP-04)
- [ ] Async work runs inside the start/stop block (TP-05, TP-15)
- [ ] `System.runAs(user) { }` for any test claiming sharing/CRUD/FLS coverage (TP-06)
- [ ] No mixed-DML between User/Profile/etc. and regular objects without runAs wrap (TP-07)
- [ ] Callout mocks registered BEFORE the call (TP-10)
- [ ] `Assert.*`, not deprecated `System.assertEquals` (TP-18)
- [ ] At least: happy path, empty/null guard, bulk (200), error path (TP-19)
- [ ] Meaningful assertions — no `Assert.areEqual(true, true)` (TP-17)
- [ ] No reliance on org-specific default data (TP-29)
- [ ] `Test.setMock` for callouts; `Test.createStub` for class mocking (TP-10, TP-27)
- [ ] REST tests set `RestContext.request/response` manually (TP-28)
