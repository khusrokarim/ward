from unittest import mock

from ward import expect, fixture
from ward.fixtures import Fixture
from ward.models import Scope, SkipMarker
from ward.suite import Suite
from ward.test_result import TestOutcome, TestResult
from ward.testing import Test, skip, test

NUMBER_OF_TESTS = 5


@fixture
def module():
    return "test_module"


@fixture
def fixture_b():
    def b():
        return 2

    return b


@fixture
def fixture_a(b=fixture_b):
    def a(b=b):
        return b * 2

    return a


@fixture
def fixtures(a=fixture_a, b=fixture_b):
    return {"fixture_a": Fixture(fn=a), "fixture_b": Fixture(fn=b)}


@fixture
def example_test(module=module, fixtures=fixtures):
    @fixture
    def f():
        return 123

    def t(fix_a=f):
        return fix_a

    return Test(fn=t, module_name=module)


@fixture
def skipped_test(module=module):
    return Test(fn=lambda: expect(1).equals(1), module_name=module, marker=SkipMarker())


@fixture
def suite(example_test=example_test):
    return Suite(tests=[example_test] * NUMBER_OF_TESTS)


@test(
    f"Suite.num_tests returns {NUMBER_OF_TESTS}, when the suite has {NUMBER_OF_TESTS} tests"
)
def _(suite=suite):
    expect(suite.num_tests).equals(NUMBER_OF_TESTS)


@test(
    f"Suite.generate_test_runs generates {NUMBER_OF_TESTS} when suite has {NUMBER_OF_TESTS} tests"
)
def _(suite=suite):
    runs = suite.generate_test_runs()

    expect(list(runs)).has_length(NUMBER_OF_TESTS)


@test("Suite.generate_test_runs generates yields the expected test results")
def _(suite=suite):
    results = list(suite.generate_test_runs())
    expected = [
        TestResult(test=test, outcome=TestOutcome.PASS, error=None, message="")
        for test in suite.tests
    ]
    expect(results).equals(expected)


@test("Suite.generate_test_runs yields a FAIL TestResult on `assert False`")
def _(module=module):
    def test_i_fail():
        assert False

    test = Test(fn=test_i_fail, module_name=module)
    failing_suite = Suite(tests=[test])

    results = failing_suite.generate_test_runs()
    result = next(results)

    expected_result = TestResult(
        test=test, outcome=TestOutcome.FAIL, error=mock.ANY, message=""
    )

    expect(result).equals(expected_result)
    expect(result.error).instance_of(AssertionError)


@test(
    "Suite.generate_test_runs yields a SKIP TestResult when test has @skip decorator "
)
def _(skipped=skipped_test, example=example_test):
    suite = Suite(tests=[example, skipped])

    test_runs = list(suite.generate_test_runs())
    expected_runs = [
        TestResult(example, TestOutcome.PASS, None, ""),
        TestResult(skipped, TestOutcome.SKIP, None, ""),
    ]

    expect(test_runs).equals(expected_runs)


@test("Suite.generate_test_runs fixture teardown code is ran in the expected order")
def _(module=module):
    events = []

    @fixture
    def fix_a():
        events.append(1)
        yield "a"
        events.append(3)

    @fixture
    def fix_b():
        events.append(2)
        return "b"

    def my_test(fix_a=fix_a, fix_b=fix_b):
        expect(fix_a).equals("a")
        expect(fix_b).equals("b")

    suite = Suite(tests=[Test(fn=my_test, module_name=module)])

    # Exhaust the test runs generator
    list(suite.generate_test_runs())

    expect(events).equals([1, 2, 3])


@test("Suite.generate_test_runs tears down deep fixtures")
def _(module=module):
    events = []

    @fixture
    def fix_a():
        events.append(1)
        yield "a"
        events.append(4)

    @fixture
    def fix_b():
        events.append(2)
        return "b"

    @fixture
    def fix_c(fix_b=fix_b):
        events.append(3)
        yield "c"
        events.append(5)

    def my_test(fix_a=fix_a, fix_c=fix_c):
        expect(fix_a).equals("a")
        expect(fix_c).equals("c")

    suite = Suite(tests=[Test(fn=my_test, module_name=module)])

    # Exhaust the test runs generator
    list(suite.generate_test_runs())

    expect(events).equals([1, 2, 3, 4, 5])


@test("Suite.generate_test_runs cached fixture isn't executed again")
def _(module=module):
    events = []

    @fixture
    def a():
        events.append(1)

    # Both of the fixtures below depend on 'a', but 'a' should only be executed once.
    @fixture
    def b(a=a):
        events.append(2)

    @fixture
    def c(a=a):
        events.append(3)

    def test(b=b, c=c):
        pass

    suite = Suite(tests=[Test(fn=test, module_name=module)])

    list(suite.generate_test_runs())

    expect(events).equals([1, 2, 3])


@test("Suite.generate_test_runs correctly tears down module scoped fixtures")
def _():
    events = []

    @fixture(scope=Scope.Module)
    def a():
        events.append("resolve")
        yield "a"
        events.append("teardown")

    def test1(a=a):
        events.append("test1")

    def test2(a=a):
        events.append("test2")

    def test3(a=a):
        events.append("test3")

    suite = Suite(
        tests=[
            Test(fn=test1, module_name="module1"),
            Test(fn=test2, module_name="module2"),
            Test(fn=test3, module_name="module2"),
        ]
    )

    list(suite.generate_test_runs())

    expect(events).equals(
        [
            "resolve",  # Resolve at start of module1
            "test1",
            "teardown",  # Teardown at end of module1
            "resolve",  # Resolve at start of module2
            "test2",
            "test3",
            "teardown",  # Teardown at end of module2
        ]
    )
    expect(len(suite.cache)).equals(0)


@test("Suite.generate_test_runs resolves and tears down global fixtures once only")
def _():
    events = []

    @fixture(scope=Scope.Global)
    def a():
        events.append("resolve")
        yield "a"
        events.append("teardown")

    def test1(a=a):
        events.append("test1")

    def test2(a=a):
        events.append("test2")

    def test3(a=a):
        events.append("test3")

    suite = Suite(
        tests=[
            Test(fn=test1, module_name="module1"),
            Test(fn=test2, module_name="module2"),
            Test(fn=test3, module_name="module2"),
        ]
    )

    list(suite.generate_test_runs())

    expect(events).equals(
        [
            "resolve",  # Resolve at start of run only
            "test1",
            "test2",
            "test3",
            "teardown",  # Teardown only at end of run
        ]
    )
    expect(len(suite.cache)).equals(0)  # Teardown includes cache cleanup


@test("Suite.generate_test_runs resolves mixed scope fixtures correctly")
def _():
    events = []

    @fixture(scope=Scope.Global)
    def a():
        events.append("resolve a")
        yield "a"
        events.append("teardown a")

    @fixture(scope=Scope.Module)
    def b():
        events.append("resolve b")
        yield "b"
        events.append("teardown b")

    @fixture(scope=Scope.Test)
    def c():
        events.append("resolve c")
        yield "c"
        events.append("teardown c")

    def test1(a=a, b=b, c=c):
        events.append("test1")

    def test2(a=a, b=b, c=c):
        events.append("test2")

    def test3(a=a, b=b, c=c):
        events.append("test3")

    suite = Suite(
        tests=[
            Test(fn=test1, module_name="module1"),
            Test(fn=test2, module_name="module2"),
            Test(fn=test3, module_name="module2"),
        ]
    )

    list(suite.generate_test_runs())

    # Note that the ordering of the final teardowns aren't well-defined
    expect(events).equals(
        [
            "resolve a",  # global fixture so resolved at start
            "resolve b",  # module fixture resolved at start of module1
            "resolve c",  # test fixture resolved at start of test1
            "test1",
            "teardown c",  # test fixture teardown at start of test1
            "teardown b",  # module fixture teardown at end of module1
            "resolve b",  # module fixture resolved at start of module2
            "resolve c",  # test fixture resolved at start of test2
            "test2",
            "teardown c",  # test fixture teardown at start of test2
            "resolve c",  # test fixture resolved at start of test3
            "test3",
            "teardown c",  # test fixture teardown at end of test3
            "teardown a",  # global fixtures are torn down at the very end
            "teardown b",  # module fixture teardown at end of module2
        ]
    )
    expect(len(suite.cache)).equals(0)


@skip("WIP")
@test(
    "Suite.generate_test_runs dependent fixtures of differing scopes behave correctly"
)
def _():
    pass
