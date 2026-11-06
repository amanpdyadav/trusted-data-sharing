import pytest

from pets_transformer.keys import DerivedKeyProvider, KeyScope, MissingKeyError
from tests.conftest import TEST_MASTER_KEY


@pytest.fixture
def keys() -> DerivedKeyProvider:
    return DerivedKeyProvider(TEST_MASTER_KEY)


def test_missing_key_fails_clearly() -> None:
    with pytest.raises(MissingKeyError, match="PETS_MASTER_KEY"):
        DerivedKeyProvider.from_env({})


def test_short_key_is_rejected() -> None:
    with pytest.raises(MissingKeyError, match="at least"):
        DerivedKeyProvider.from_env({"PETS_MASTER_KEY": "short"})


def test_each_domain_gets_its_own_key(keys: DerivedKeyProvider) -> None:
    assert keys.key_for("A") == keys.key_for("A")
    assert keys.key_for("A") != keys.key_for("B")


def test_empty_domain_is_rejected(keys: DerivedKeyProvider) -> None:
    with pytest.raises(ValueError, match="empty"):
        keys.key_for("")


def test_seed_is_reproducible_secret_and_purpose_specific(keys: DerivedKeyProvider) -> None:
    scope = KeyScope(keys, "S2/public/w1")
    assert scope.seed("dp/a") == scope.seed("dp/a")
    assert scope.seed("dp/a") != scope.seed("dp/b")
    assert scope.seed("dp/a") != KeyScope(keys, "S2/public/w2").seed("dp/a")
    assert scope.seed("dp/a") != KeyScope(DerivedKeyProvider(b"y" * 40), "S2/public/w1").seed("dp/a")
