# -*- encoding: utf-8 -*-
"""Tests for Installer

:Requirement: Installer

:CaseAutomation: Automated

:CaseLevel: Acceptance

:CaseComponent: CLI

:TestType: Functional

:CaseImportance: High

:Upstream: No
"""
from robottelo.decorators import run_only_on, stubbed
from robottelo.test import CLITestCase


class InstallerTestCase(CLITestCase):
    """Test class for installer"""
    # Notes for installer testing:
    # Perhaps there is a convenient log analyzer library out there
    # that can parse logs? It would be better (and possibly less
    # error-prone) than simply grepping for ERROR/FATAL

    @stubbed()
    @run_only_on('sat')
    def test_positive_installer_check_services(self):
        # devnote:
        # maybe `hammer ping` command might be useful here to check
        # the health status
        """Services services start correctly

        :id: d3f99d2d-8e87-47c4-b80e-151edac5b0c3

        :assert: All services {katello-jobs, tomcat6, foreman, pulp,
            passenger-analytics, httpd, foreman_proxy, elasticsearch,
            postgresql, mongod} are started

        :caseautomation: notautomated
        """

    @stubbed()
    @run_only_on('sat')
    def test_positive_installer_logfile_check(self):
        """Look for ERROR or FATAL references in logfiles

        :id: fe29310d-7fe2-4563-bd4b-ecebc0a24f7f

        :steps: search all relevant logfiles for ERROR/FATAL

        :assert: No ERROR/FATAL notifcations occur in {katello-jobs, tomcat6,
            foreman, pulp, passenger-analytics,httpd, foreman_proxy,
            elasticsearch, postgresql, mongod} logfiles.

        :caseautomation: notautomated
        """

    @stubbed()
    @run_only_on('sat')
    def test_positive_installer_check_progress_meter(self):
        """ Assure progress indicator/meter "works"

        :id: c654be1b-d018-4eb4-9867-6ecbb0a8ae5a

        :assert: Progress indicator increases appropriately as install
            commences, through to completion

        :caseautomation: notautomated
        """

    @stubbed()
    @run_only_on('sat')
    def test_positive_server_installer_from_iso(self):
        """ Can install product from ISO

        :id: 38c08646-9f71-48d9-a9c2-66bd94c3e5bb

        :assert: Install from ISO is sucessful.

        :caseautomation: notautomated
        """

    @stubbed()
    @run_only_on('sat')
    def test_positive_server_installer_from_repository(self):
        """ Can install main satellite instance successfully via RPM

        :id: 4dac99c3-6334-43df-adc4-c26e19f762ce

        :assert: Install of main instance successful.

        :caseautomation: notautomated
        """

    @stubbed()
    @run_only_on('sat')
    def test_positive_capsule_installer_from_repository(self):
        """ Can install capsule successfully via RPM

        :id: 07b0aaa3-651a-4103-904d-c8bcc632a3d1

        :assert: Install of capsule successful.

        :caseautomation: notautomated
        """

    @stubbed()
    @run_only_on('sat')
    def test_positive_disconnected_util_installer(self):
        """ Can install  satellite disconnected utility successfully
        via RPM

        :id: b738cf2a-9c5f-4865-b134-102a4688534c

        :assert: Install of disconnected utility successful.

        :caseautomation: notautomated
        """

    @stubbed()
    @run_only_on('sat')
    def test_positive_capsule_installer_and_register(self):
        """Upon installation, capsule instance self-registers
        itself to parent instance

        :id: efd03442-5a08-445d-b257-e4d346084379

        :assert: capsule is communicating properly with parent, following
            install.

        :caseautomation: notautomated
        """

    @stubbed()
    @run_only_on('sat')
    def test_positive_installer_clear_data(self):
        """ User can run installer to clear existing data

        :id: 11ed1ed5-7f72-4310-80df-5cac6547b01a

        :assert: All data is cleared from satellite instance

        :bz: 1072780

        :caseautomation: notautomated
        """
