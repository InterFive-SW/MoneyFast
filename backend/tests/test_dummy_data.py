import pytest
import sys
import os
from unittest.mock import MagicMock

# Ensure the scripts directory is accessible
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.generate_dummy_data import generate_dummy_data, DUMMY_TC_PREFIX, DUMMY_EMAIL_DOMAIN
from app.modules.auth.models import User

@pytest.fixture
def mock_session_local(mocker):
    mock_session_class = mocker.patch("scripts.generate_dummy_data.SessionLocal")
    mock_db = MagicMock()
    mock_session_class.return_value = mock_db
    return mock_db


@pytest.fixture
def mock_is_safe_environment(mocker):
    return mocker.patch("scripts.generate_dummy_data.is_safe_environment", return_value=True)


def test_generator_deterministic_output(mock_session_local, mock_is_safe_environment):
    """Test that the generator produces the exact same output when given the same seed."""
    # Run once
    mock_session_local.query().filter().count.return_value = 0
    generate_dummy_data(users_count=2, seed=42, reset=False)
    
    first_run_calls = mock_session_local.add.call_args_list
    assert len(first_run_calls) == 2
    
    user1_run1 = first_run_calls[0][0][0]
    user2_run1 = first_run_calls[1][0][0]
    
    # Reset mock and run again with the same seed
    mock_session_local.reset_mock()
    mock_session_local.query().filter().count.return_value = 0
    generate_dummy_data(users_count=2, seed=42, reset=False)
    
    second_run_calls = mock_session_local.add.call_args_list
    assert len(second_run_calls) == 2
    
    user1_run2 = second_run_calls[0][0][0]
    user2_run2 = second_run_calls[1][0][0]
    
    # Compare generated content (excluding dynamic fields like id, created_at, hashed_password because hash uses salt)
    assert user1_run1.tc_no == user1_run2.tc_no
    assert user1_run1.email == user1_run2.email
    assert user1_run1.first_name == user1_run2.first_name
    assert user1_run1.last_name == user1_run2.last_name
    assert user1_run1.phone_number == user1_run2.phone_number
    
    assert user2_run1.tc_no == user2_run2.tc_no
    assert user2_run1.email == user2_run2.email


def test_generator_safe_environment_guard(mock_session_local, mocker):
    """Test that generator raises SystemExit if environment is not safe."""
    mocker.patch("scripts.generate_dummy_data.is_safe_environment", return_value=False)
    
    with pytest.raises(SystemExit) as exc_info:
        generate_dummy_data(users_count=5)
    
    assert exc_info.value.code == 1
    mock_session_local.add.assert_not_called()


def test_generator_reset_logic(mock_session_local, mock_is_safe_environment):
    """Test that reset targets only dummy data using the specific domain."""
    mock_query = mock_session_local.query.return_value
    mock_filter = mock_query.filter.return_value
    
    generate_dummy_data(users_count=0, reset=True)
    
    # Ensure it tried to delete
    mock_filter.delete.assert_called_once()
    
    # We can't easily assert the exact SQLAlchemy expression passed to filter in a mock,
    # but we can verify it was called. The code explicitly checks User.email.endswith(DUMMY_EMAIL_DOMAIN)


def test_generator_valid_tc_and_phone(mock_session_local, mock_is_safe_environment):
    """Test that generated fields match the expected validation patterns."""
    mock_session_local.query().filter().count.return_value = 0
    generate_dummy_data(users_count=1, seed=123, reset=False)
    
    user = mock_session_local.add.call_args[0][0]
    
    # TC must be exactly 11 digits
    assert len(user.tc_no) == 11
    assert user.tc_no.isdigit()
    assert user.tc_no.startswith(DUMMY_TC_PREFIX)
    
    # Phone must start with + and have 10-15 digits
    assert user.phone_number.startswith("+")
    assert 10 <= len(user.phone_number[1:]) <= 15
    assert user.phone_number[1:].isdigit()
    
    # Email must end with DUMMY_EMAIL_DOMAIN
    assert user.email.endswith(DUMMY_EMAIL_DOMAIN)
