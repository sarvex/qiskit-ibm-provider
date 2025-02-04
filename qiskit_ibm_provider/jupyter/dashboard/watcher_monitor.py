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

"""A module of widgets for job monitoring."""

import sys
import threading
import time

from qiskit.providers.jobstatus import JobStatus

from qiskit_ibm_provider.job.ibm_job import IBMJob
from ...utils.converters import duration_difference


def _job_monitor(job: IBMJob, status: JobStatus, watcher: "IBMDashboard") -> None:
    """Monitor the status of an ``IBMJob`` instance.

    Args:
        job: Job to monitor.
        status: Job status.
        watcher: Job watcher instance.
    """
    thread = threading.Thread(target=_job_checker, args=(job, status, watcher))
    thread.start()


def _job_checker(job: IBMJob, status: JobStatus, watcher: "IBMDashboard") -> None:
    """A simple job status checker.

    Args:
        job: The job to check.
        status: Job status.
        watcher: Job watcher instance.
    """
    prev_status_name = None
    prev_queue_pos = None
    interval = 2
    exception_count = 0
    prev_est_time = ""
    while status.name not in ["DONE", "CANCELLED", "ERROR"]:
        time.sleep(interval)
        try:
            status = job.status()
            exception_count = 0

            if status.name == "QUEUED":
                queue_pos = job.queue_position()
                if queue_pos != prev_queue_pos:
                    queue_info = job.queue_info()
                    if queue_info and queue_info.estimated_start_time:
                        est_time = duration_difference(queue_info.estimated_start_time)
                        prev_est_time = est_time
                    else:
                        est_time = prev_est_time

                    update_info = (
                        job.job_id(),
                        f"{status.name} ({queue_pos})",
                        est_time,
                        status.value,
                    )

                    watcher.update_single_job(update_info)
                    interval = max(queue_pos, 2) if queue_pos is not None else 2
                    prev_queue_pos = queue_pos

            elif status.name != prev_status_name:
                msg = status.name
                if msg == "RUNNING":
                    if job_mode := job.scheduling_mode():
                        msg += f" [{job_mode[0].upper()}]"

                update_info = (job.job_id(), msg, 0, status.value)

                watcher.update_single_job(update_info)
                interval = 2
                prev_status_name = status.name

        except Exception:
            exception_count += 1
            if exception_count == 5:
                update_info = (job.job_id(), "NA", 0, "Could not query job.")
                watcher.update_single_job(update_info)
                sys.exit()
