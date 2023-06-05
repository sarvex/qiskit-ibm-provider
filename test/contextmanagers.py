# This code is part of Qiskit.
#
# (C) Copyright IBM 2021.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Context managers for using with IBM Provider unit tests."""

import os
from contextlib import ContextDecorator, contextmanager
from typing import Optional, Dict, Any
from unittest.mock import patch

from qiskit_ibm_provider import IBMProvider


class custom_envs(ContextDecorator):
    """Context manager that modifies environment variables."""

    # pylint: disable=invalid-name

    def __init__(self, new_environ):
        """custom_envs constructor.

        Args:
            new_environ (dict): a dictionary of new environment variables to
                use.
        """
        self.new_environ = new_environ
        self.os_environ_original = os.environ.copy()

    def __enter__(self):
        # Remove the original variables from `os.environ`.
        modified_environ = {**os.environ, **self.new_environ}
        os.environ = modified_environ

    def __exit__(self, *exc):
        os.environ = self.os_environ_original


class no_envs(ContextDecorator):
    """Context manager that disables environment variables."""

    # pylint: disable=invalid-name

    def __init__(self, vars_to_remove):
        """no_envs constructor.

        Args:
            vars_to_remove (list): environment variables to remove.
        """
        self.vars_to_remove = vars_to_remove
        self.os_environ_original = os.environ.copy()

    def __enter__(self):
        # Remove the original variables from `os.environ`.
        modified_environ = {
            key: value
            for key, value in os.environ.items()
            if key not in self.vars_to_remove
        }
        os.environ = modified_environ

    def __exit__(self, *exc):
        os.environ = self.os_environ_original


class no_file(ContextDecorator):
    """Context manager that disallows access to a file."""

    # pylint: disable=invalid-name

    def __init__(self, filename):
        self.filename = filename
        # Store the original `os.path.isfile` function, for mocking.
        self.isfile_original = os.path.isfile
        self.patcher = patch("os.path.isfile", side_effect=self.side_effect)

    def __enter__(self):
        self.patcher.start()

    def __exit__(self, *exc):
        self.patcher.stop()

    def side_effect(self, filename_):
        """Return False for the specified file."""
        return False if filename_ == self.filename else self.isfile_original(filename_)


def _mock_initialize_hgps(self: Any, preferences: Optional[Dict] = None) -> None:
    """Mock ``_initialize_hgps()``, just storing the credentials."""
    # TODO - update mock initialization
    hgp: Any = {}
    self._hgp = hgp
    self._hgps = {}
        # credentials.preferences = preferences.get(credentials.unique_id(), {})


@contextmanager
def mock_ibm_provider():
    """Mock the initialization of ``IBMProvider``, so it does not query the API."""
    patcher = patch.object(
        IBMProvider,
        "_initialize_hgps",
        side_effect=_mock_initialize_hgps,
        autospec=True,
    )
    patcher2 = patch.object(
        IBMProvider,
        "_check_api_version",
        return_value={"new_api": True, "api-auth": "0.1"},
    )
    patcher.start()
    patcher2.start()
    yield
    patcher2.stop()
    patcher.stop()
