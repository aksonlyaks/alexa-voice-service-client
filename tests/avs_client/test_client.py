from io import BytesIO
import functools
from unittest.mock import call, patch, Mock, MagicMock

import pytest

from avs_client.avs_client import client, connection


class TestAlexaVoiceServiceClient(client.AlexaVoiceServiceClient):
    authentication_manager_class = Mock(return_value=Mock(
        spec_set=client.AlexaVoiceServiceClient.authentication_manager_class
    ))
    device_manager_class = Mock(return_value=Mock(
        spec_set=client.AlexaVoiceServiceClient.device_manager_class
    ))
    connection_manager_class = Mock(return_value=Mock(
        spec_set=client.AlexaVoiceServiceClient.connection_manager_class
    ))
    ping_manager_class = Mock(return_value=Mock(
        spec_set=client.AlexaVoiceServiceClient.ping_manager_class,
    ))


@pytest.fixture
def client():
    client = TestAlexaVoiceServiceClient(
        client_id='test_client_id',
        secret='test_secret',
        refresh_token='test_refresh_token',
    )
    # reset call counts.
    client.authentication_manager.reset_mock()
    client.device_manager.reset_mock()
    client.connection_manager.reset_mock()
    client.ping_manager.reset_mock()
    client.ping_manager.update_ping_deadline = MagicMock()  # context manager
    return client


def test_client_authentication_manager(client):
    assert client.authentication_manager_class.call_count == 1
    assert client.authentication_manager_class.call_args == call(
        client_id='test_client_id',
        secret='test_secret',
        refresh_token='test_refresh_token',
    )


def test_client_connect(client):
    client.connect()

    assert client.authentication_manager.prefetch_api_token.call_count == 1
    assert client.connection_manager.establish_downchannel_stream.call_count == 1
    assert client.connection_manager.synchronise_device_state.call_count == 1


def test_client_establish_downchannel_stream(client):
    client.authentication_manager.get_headers.return_value = {'auth': 'value'}

    client.establish_downchannel_stream()

    assert client.connection_manager.establish_downchannel_stream.call_args == call(
        authentication_headers={'auth': 'value'}
    )


def test_client_synchronise_device_state(client):
    client.authentication_manager.get_headers.return_value = {'auth': 'value'}
    client.device_manager.get_device_state.return_value = {'device': 'state'}

    client.synchronise_device_state()

    assert client.connection_manager.synchronise_device_state.call_args == call(
        device_state={'device': 'state'},
        authentication_headers={'auth': 'value'},
    )
    assert client.ping_manager.update_ping_deadline.call_count == 1


def test_client_send_audio_file(client):
    client.authentication_manager.get_headers.return_value = {'auth': 'value'}
    client.device_manager.get_device_state.return_value = {'device': 'state'}

    audio_file = BytesIO(b'things')
    client.send_audio_file(audio_file)

    assert client.connection_manager.send_audio_file.call_args == call(
        audio_file=audio_file,
        device_state={'device': 'state'},
        authentication_headers={'auth': 'value'},
    )
    assert client.ping_manager.update_ping_deadline.call_count == 1


def test_conditional_ping_should_not_ping(client):
    client.ping_manager.should_ping.return_value = False

    client.conditional_ping()

    assert client.connection_manager.ping.call_count == 0
    assert client.ping_manager.update_ping_deadline.call_count == 0


def test_conditional_ping_should_ping(client):
    client.ping_manager.should_ping.return_value = True

    client.conditional_ping()

    assert client.connection_manager.ping.call_count == 1
    assert client.ping_manager.update_ping_deadline.call_count == 1


def test_conditional_ping_decorated(client):
    assert client.conditional_ping.__wrapped__.__name__ == 'conditional_ping'


def test_conditional_ping_single_reset_retry(client):
    client.connect = Mock()

    side_effects = [
        connection.StreamResetError(),
        Mock(status=204),
    ]

    client.ping_manager.should_ping.return_value = True
    client.connection_manager.ping.side_effect = side_effects

    actual = client.conditional_ping()

    assert actual == side_effects[-1]
    assert client.connect.call_count == 1
    assert client.ping_manager.update_ping_deadline.call_count == 2
    assert client.connection_manager.ping.call_count == 2


def test_conditional_ping_multiple_reset_not_retry(client):
    client.connect = Mock()

    side_effects = [
        connection.StreamResetError(),
        connection.StreamResetError(),
    ]

    client.ping_manager.should_ping.return_value = True
    client.connection_manager.ping.side_effect = side_effects

    with pytest.raises(connection.StreamResetError):
        actual = client.conditional_ping()
