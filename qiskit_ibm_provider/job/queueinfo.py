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

"""Queue information for a job."""

import warnings
from datetime import datetime
from typing import Any, Optional, Union, Dict

import dateutil.parser

from ..utils import utc_to_local, duration_difference
from ..utils.utils import api_status_to_job_status


class QueueInfo:
    """Queue information for a job."""

    _data = {}  # type: Dict

    def __init__(
        self,
        position_in_queue: Optional[int] = None,
        status: Optional[str] = None,
        estimated_start_time: Optional[Union[str, datetime]] = None,
        estimated_completion_time: Optional[Union[str, datetime]] = None,
        hub_priority: Optional[float] = None,
        group_priority: Optional[float] = None,
        project_priority: Optional[float] = None,
        job_id: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """QueueInfo constructor.

        Args:
            position: Position in the queue.
            status: Job status.
            estimated_start_time: Estimated start time for the job, in UTC.
            estimated_complete_time: Estimated complete time for the job, in UTC.
            hub_priority: Dynamic priority for the hub.
            group_priority: Dynamic priority for the group.
            project_priority: Dynamic priority for the project.
            job_id: Job ID.
            kwargs: Additional attributes.
        """
        self.position = int(position_in_queue) if position_in_queue else None
        self._status = status
        if isinstance(estimated_start_time, str):
            estimated_start_time = dateutil.parser.isoparse(estimated_start_time)
        if isinstance(estimated_completion_time, str):
            estimated_completion_time = dateutil.parser.isoparse(
                estimated_completion_time
            )
        self._estimated_start_time_utc = estimated_start_time
        self._estimated_complete_time_utc = estimated_completion_time
        self.hub_priority = hub_priority
        self.group_priority = group_priority
        self.project_priority = project_priority
        self.job_id = job_id

        self._data = kwargs

    def __repr__(self) -> str:
        """Return the string representation of ``QueueInfo``.

        Note:
            The estimated start and end time are displayed in local time
            for convenience.

        Returns:
            A string representation of ``QueueInfo``.

        Raises:
            TypeError: If the `estimated_start_time` or `estimated_end_time`
                value is not valid.
        """
        status = (
            api_status_to_job_status(self._status).name
            if self._status
            else self._get_value(self._status)
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            est_start_time = (
                self.estimated_start_time.isoformat()
                if self.estimated_start_time
                else None
            )
            est_complete_time = (
                self.estimated_complete_time.isoformat()
                if self.estimated_complete_time
                else None
            )

        queue_info = [
            f"job_id='{self.job_id}'",
            f"_status='{status}'",
            f"estimated_start_time='{est_start_time}'",
            f"estimated_complete_time='{est_complete_time}'",
            f"position={self.position}",
            f"hub_priority={self.hub_priority}",
            f"group_priority={self.group_priority}",
            f"project_priority={self.project_priority}",
        ]

        return f'<{self.__class__.__name__}({", ".join(queue_info)})>'

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"Attribute {name} is not defined.") from None

    def format(self) -> str:
        """Build a user-friendly report for the job queue information.

        Returns:
             The job queue information report.
        """
        status = (
            api_status_to_job_status(self._status).value
            if self._status
            else self._get_value(self._status)
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            est_start_time = (
                duration_difference(self.estimated_start_time)
                if self.estimated_start_time
                else self._get_value(self.estimated_start_time)
            )
            est_complete_time = (
                duration_difference(self.estimated_complete_time)
                if self.estimated_complete_time
                else self._get_value(self.estimated_complete_time)
            )

        queue_info = [
            f"Job {self._get_value(self.job_id)} queue information:",
            f"    queue position: {self._get_value(self.position)}",
            f"    status: {status}",
            f"    estimated start time: {est_start_time}",
            f"    estimated completion time: {est_complete_time}",
            f"    hub priority: {self._get_value(self.hub_priority)}",
            f"    group priority: {self._get_value(self.group_priority)}",
            f"    project priority: {self._get_value(self.project_priority)}",
        ]

        return "\n".join(queue_info)

    def _get_value(
        self, value: Optional[Any], default_value: str = "unknown"
    ) -> Optional[Any]:
        """Return the input value if it exists or the default.

        Returns:
            The input value if it is not ``None``, else the input default value.
        """
        return value or default_value

    @property
    def estimated_start_time(self) -> Optional[datetime]:
        """Return estimated start time in local time."""
        if self._estimated_start_time_utc is None:
            return None
        return utc_to_local(self._estimated_start_time_utc)

    @property
    def estimated_complete_time(self) -> Optional[datetime]:
        """Return estimated complete time in local time."""
        if self._estimated_complete_time_utc is None:
            return None
        return utc_to_local(self._estimated_complete_time_utc)
