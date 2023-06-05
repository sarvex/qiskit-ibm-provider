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

"""Test IBMJob attributes."""

import re
import time
import uuid
from datetime import datetime, timedelta
from unittest import mock, skip

from dateutil import tz
from qiskit.compiler import transpile
from qiskit.providers.jobstatus import JobStatus, JOB_FINAL_STATES
from qiskit.test.reference_circuits import ReferenceCircuits

from qiskit_ibm_provider.api.clients.runtime import RuntimeClient
from qiskit_ibm_provider.exceptions import (
    IBMBackendValueError,
    IBMBackendApiProtocolError,
)
from qiskit_ibm_provider.job.exceptions import IBMJobFailureError
from ..decorators import (
    IntegrationTestDependencies,
    integration_test_setup,
)
from ..fake_account_client import BaseFakeAccountClient, MissingFieldFakeJob
from ..ibm_test_case import IBMTestCase
from ..utils import (
    most_busy_backend,
    cancel_job,
    submit_job_bad_shots,
    submit_job_one_bad_instr,
)


class TestIBMJobAttributes(IBMTestCase):
    """Test IBMJob instance attributes."""

    @classmethod
    @integration_test_setup()
    def setUpClass(cls, dependencies: IntegrationTestDependencies) -> None:
        """Initial class level setup."""
        # pylint: disable=arguments-differ
        super().setUpClass()
        cls.dependencies = dependencies
        cls.sim_backend = dependencies.provider.get_backend(
            "ibmq_qasm_simulator", instance=dependencies.instance
        )
        cls.bell = transpile(ReferenceCircuits.bell(), cls.sim_backend)
        cls.sim_job = cls.sim_backend.run(cls.bell)
        cls.last_week = datetime.now() - timedelta(days=7)

    def setUp(self):
        """Initial test setup."""
        super().setUp()
        self._qc = ReferenceCircuits.bell()

    def test_job_id(self):
        """Test getting a job ID."""
        self.assertTrue(self.sim_job.job_id() is not None)

    def test_get_backend_name(self):
        """Test getting a backend name."""
        self.assertTrue(self.sim_job.backend().name == self.sim_backend.name)

    @skip("Skip until aer issue 1214 is fixed")
    def test_error_message_simulator(self):
        """Test retrieving job error messages from a simulator backend."""
        job = submit_job_one_bad_instr(self.sim_backend)
        with self.assertRaises(IBMJobFailureError) as err_cm:
            job.result()
        self.assertNotIn("bad_instruction", err_cm.exception.message)

        message = job.error_message()
        self.assertIn("Experiment 1: ERROR", message)

        r_message = self.provider.backend.retrieve_job(job.job_id()).error_message()
        self.assertIn("Experiment 1: ERROR", r_message)

    @skip("not supported by api")
    def test_error_message_validation(self):
        """Test retrieving job error message for a validation error."""
        job = submit_job_bad_shots(self.sim_backend)
        rjob = self.dependencies.provider.retrieve_job(job.job_id())

        for q_job, partial in [(job, False), (rjob, True)]:
            with self.subTest(partial=partial):
                with self.assertRaises(IBMJobFailureError) as err_cm:
                    q_job.result(partial=partial)
                for msg in (err_cm.exception.message, q_job.error_message()):
                    self.assertNotIn("Unknown", msg)
                    self.assertIsNotNone(
                        re.search(r"Error code: [0-9]{4}\.$", msg), msg
                    )

        self.assertEqual(job.error_message(), rjob.error_message())

    @skip("time_per_step not supported by the api")
    def test_refresh(self):
        """Test refreshing job data."""
        self.sim_job._wait_for_completion()
        if "COMPLETED" not in self.sim_job.time_per_step():
            self.sim_job.refresh()

        rjob = self.dependencies.provider.backend.retrieve_job(self.sim_job.job_id())
        rjob.refresh()
        self.assertEqual(rjob._time_per_step, self.sim_job._time_per_step)

    def test_job_creation_date(self):
        """Test retrieving creation date, while ensuring it is in local time."""
        # datetime, before running the job, in local time.
        start_datetime = datetime.now().replace(tzinfo=tz.tzlocal()) - timedelta(
            seconds=1
        )
        job = self.sim_backend.run(self.bell)
        job.result()
        # datetime, after the job is done running, in local time.
        end_datetime = datetime.now().replace(tzinfo=tz.tzlocal()) + timedelta(
            seconds=1
        )

        self.assertTrue(
            start_datetime <= job.creation_date() <= end_datetime,
            f"job creation date {job.creation_date()} is not between the start date time {start_datetime} and end date time {end_datetime}",
        )

    def test_time_per_step(self):
        """Test retrieving time per step, while ensuring the date times are in local time."""
        # datetime, before running the job, in local time.
        start_datetime = datetime.now().replace(tzinfo=tz.tzlocal()) - timedelta(
            seconds=1
        )
        job = self.sim_backend.run(self.bell)
        job.result()
        # datetime, after the job is done running, in local time.
        end_datetime = datetime.now().replace(tzinfo=tz.tzlocal()) + timedelta(
            seconds=1
        )

        self.assertTrue(job.time_per_step())
        for step, time_data in job.time_per_step().items():
            self.assertTrue(
                start_datetime <= time_data <= end_datetime,
                f'job time step "{step}={time_data}" is not between the start date time {start_datetime} and end date time {end_datetime}',
            )

        rjob = self.dependencies.provider.backend.retrieve_job(job.job_id())
        self.assertTrue(rjob.time_per_step())

    @skip("need attributes not supported")
    def test_new_job_attributes(self):
        """Test job with new attributes."""

        def _mocked__api_job_submit(*args, **kwargs):
            submit_info = original_submit(*args, **kwargs)
            submit_info.update({"batman": "bruce"})
            return submit_info

        original_submit = self.sim_backend._api_client.job_submit
        with mock.patch.object(
            RuntimeClient, "job_submit", side_effect=_mocked__api_job_submit
        ):
            job = self.sim_backend.run(self.bell)

        self.assertEqual(job.batman_, "bruce")

    def test_queue_info(self):
        """Test retrieving queue information."""
        # Find the most busy backend.
        backend = most_busy_backend(self.dependencies.provider)
        leave_states = list(JOB_FINAL_STATES) + [JobStatus.RUNNING]
        job = backend.run(self.bell)
        queue_info = None
        for _ in range(20):
            queue_info = job.queue_info()
            # Even if job status is queued, its queue info may not be immediately available.
            if (
                job._status is JobStatus.QUEUED and job.queue_position() is not None
            ) or job._status in leave_states:
                break
            time.sleep(1)

        if job._status is JobStatus.QUEUED and job.queue_position() is not None:
            self.log.debug(
                "Job id=%s, queue info=%s, queue position=%s",
                job.job_id(),
                queue_info,
                job.queue_position(),
            )
            msg = f"Job {job.job_id()} is queued but has no "
            self.assertIsNotNone(queue_info, f"{msg}queue info.")
            for attr, value in queue_info.__dict__.items():
                self.assertIsNotNone(value, msg + attr)
            self.assertTrue(
                all(
                    0 < priority <= 1.0
                    for priority in [
                        queue_info.hub_priority,
                        queue_info.group_priority,
                        queue_info.project_priority,
                    ]
                ),
                f"Unexpected queue info {queue_info} for job {job.job_id()}",
            )

            self.assertTrue(queue_info.format())
            self.assertTrue(repr(queue_info))
        elif job._status is not None:
            self.assertIsNone(job.queue_position())
            self.log.warning("Unable to retrieve queue information")

        # Cancel job so it doesn't consume more resources.
        cancel_job(job)

    def test_esp_readout_not_enabled(self):
        """Test that an error is thrown is ESP readout is used and the backend does not support it."""
        saved_api = self.sim_backend._api_client
        try:
            self.sim_backend._api_client = BaseFakeAccountClient()
            # sim backend does not have ``measure_esp_enabled`` flag: defaults to ``False``
            with self.assertRaises(IBMBackendValueError) as context_manager:
                self.sim_backend.run(self.bell, use_measure_esp=True)
            self.assertIn(
                "ESP readout not supported on this device. Please make sure the flag "
                "'use_measure_esp' is unset or set to 'False'.",
                context_manager.exception.message,
            )
        finally:
            self.sim_backend._api_client = saved_api

    @skip("not supported by api")
    def test_esp_readout_enabled(self):
        """Test that ESP readout can be used when the backend supports it."""
        saved_api = self.sim_backend._api_client
        try:
            self.sim_backend._api_client = BaseFakeAccountClient()
            setattr(self.sim_backend._configuration, "measure_esp_enabled", True)
            job = self.sim_backend.run(self.bell, use_measure_esp=True)
            self.assertEqual(job.backend_options()["use_measure_esp"], True)
        finally:
            delattr(self.sim_backend._configuration, "measure_esp_enabled")
            self.sim_backend._api_client = saved_api

    @skip("not supported by api")
    def test_esp_readout_default_value(self):
        """Test that ESP readout is set to backend support value if not specified."""
        saved_api = self.sim_backend._api_client
        try:
            self.sim_backend._api_client = BaseFakeAccountClient()
            # ESP readout not enabled on backend
            setattr(self.sim_backend._configuration, "measure_esp_enabled", False)
            job = self.sim_backend.run(self.bell)
            self.assertEqual(job.backend_options()["use_measure_esp"], False)
            # ESP readout enabled on backend
            setattr(self.sim_backend._configuration, "measure_esp_enabled", True)
            job = self.sim_backend.run(self.bell)
            self.assertEqual(job.backend_options()["use_measure_esp"], True)
        finally:
            delattr(self.sim_backend._configuration, "measure_esp_enabled")
            self.sim_backend._api_client = saved_api

    @skip("not supported by api")
    def test_esp_readout_enabled_not_used(self):
        """Test that ESP readout is not used if user sets to ``False``, even if backend supports it."""
        saved_api = self.sim_backend._api_client
        try:
            self.sim_backend._api_client = BaseFakeAccountClient()
            setattr(self.sim_backend._configuration, "measure_esp_enabled", True)
            job = self.sim_backend.run(self.bell, use_measure_esp=False)
            self.assertEqual(job.backend_options()["use_measure_esp"], False)
        finally:
            delattr(self.sim_backend._configuration, "measure_esp_enabled")
            self.sim_backend._api_client = saved_api

    def test_job_tags(self):
        """Test using job tags."""
        # Use a unique tag.
        job_tags = [
            uuid.uuid4().hex[:16],
            uuid.uuid4().hex[:16],
            uuid.uuid4().hex[:16],
        ]
        job = self.sim_backend.run(self.bell, job_tags=job_tags)

        no_rjobs_tags = [job_tags[:1] + ["phantom_tags"], ["phantom_tag"]]
        for tags in no_rjobs_tags:
            rjobs = self.dependencies.provider.backend.jobs(
                job_tags=tags, start_datetime=self.last_week
            )
            self.assertEqual(len(rjobs), 0, f"Expected job {job.job_id()}, got {rjobs}")

        has_rjobs_tags = [job_tags, job_tags[1:3]]
        for tags in has_rjobs_tags:
            with self.subTest(tags=tags):
                rjobs = self.dependencies.provider.backend.jobs(
                    job_tags=tags,
                    start_datetime=self.last_week,
                )
                self.assertEqual(len(rjobs), 1, f"Expected job {job.job_id()}, got {rjobs}")
                self.assertEqual(rjobs[0].job_id(), job.job_id())
                # TODO check why this sometimes fails
                # self.assertEqual(set(rjobs[0].tags()), set(job_tags))

    def test_job_tags_replace(self):
        """Test updating job tags by replacing a job's existing tags."""
        initial_job_tags = [uuid.uuid4().hex[:16]]
        job = self.sim_backend.run(self.bell, job_tags=initial_job_tags)

        tags_to_replace_subtests = [
            [],
            [f"{uuid.uuid4().hex[:5]}_new_tag_{i}" for i in range(2)],
            initial_job_tags + ["foo"],
        ]
        for tags_to_replace in tags_to_replace_subtests:
            with self.subTest(tags_to_replace=tags_to_replace):
                # Update the job tags.
                _ = job.update_tags(new_tags=tags_to_replace)

                # Wait a bit so we don't get cached results.
                time.sleep(2)
                job.refresh()

                self.assertEqual(set(tags_to_replace), set(job.tags()))

    def test_invalid_job_tags(self):
        """Test using job tags with an and operator."""
        self.assertRaises(
            IBMBackendValueError, self.sim_backend.run, self.bell, job_tags={"foo"}
        )
        self.assertRaises(
            IBMBackendValueError,
            self.dependencies.provider.backend.jobs,
            job_tags=[1, 2, 3],
        )

    @skip("TODO refactor fake client")
    def test_missing_required_fields(self):
        """Test response data is missing required fields."""
        saved_api = self.sim_backend._api_client
        try:
            self.sim_backend._api_client = BaseFakeAccountClient(
                job_class=MissingFieldFakeJob
            )
            self.assertRaises(
                IBMBackendApiProtocolError, self.sim_backend.run, self.bell
            )
        finally:
            self.sim_backend._api_client = saved_api

    @skip("not supported by api")
    def test_client_version(self):
        """Test job client version information."""
        self.assertIsNotNone(self.sim_job.result().client_version)
        self.assertIsNotNone(self.sim_job.client_version)
