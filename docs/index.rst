Robottelo
=========

`Robottelo`_ is a test suite which exercises `The Foreman`_. All tests are
automated, suited for use in a continuous integration environment, and `data
driven`_. There are three types of tests:

* UI tests, which rely on Selenium's `WebDriver`_.
* CLI tests, which rely on `ssh2-python`_.
* API tests, which rely on `Requests`_.

.. contents::

Quickstart
==========

The following is only a brief setup guide for `Robottelo`_. The section on
`Running the Tests`_ provides a more comprehensive guide to using Robottelo.

Robottelo requires SSH access to the Satellite system under test, and this
SSH access is implemented by ssh2-python. Install the headers for the following to
ensure that ssh2-python's dependencies build correctly:

* OpenSSL
* Python development headers


Recommendation: Create a virtual python environment for the following setup.

Create virtual environment for python 3.x::
$ python3 -m venv <venv_name>
To activate virtual environment:
$ source <venv_name>/bin/activate
To end the session:
$ deactivate

On Fedora, you can install these with the following command:

For python3.x::
dnf install -y gcc git libffi-devel openssl-devel python38-devel \
redhat-rpm-config libcurl-devel libxml2-devel

Get the source code and install dependencies::

$ git clone git://github.com/SatelliteQE/robottelo.git
$ export PYCURL_SSL_LIBRARY=<ssl library>
$ pip install -r requirements.txt

**Notes:**
* To determine ssl library, check http://pycurl.io/docs/latest/install.html#ssl

That's it! You can now go ahead and start testing The Foreman. However, there
are a few other things you may wish to do before continuing:

1. You may want to install development tools (such as gcc) for your OS. If
running Fedora or Red Hat Enterprise Linux, execute ``yum groupinstall
"Development Tools"``. Make sure to use ``dnf`` instead of ``yum`` if
``dnf`` is available on your system.
2. You may wish to install the optional dependencies listed in
``requirements-optional.txt``. (Use pip, as shown above.) They are required
for tasks like working with certificates, running the internal robottelo test
suite and checking code quality with pre-commit.

Robottelo on Docker
-------------------

Robottelo is also available on `dockerhub`_.::

$ docker pull satelliteqe/robottelo

It also can be built locally using the Dockerfile, in the main directory.::

$ docker build -t robottelo .

In order to run tests, you will need to mount your robottelo.properties file.::

$ docker run -v {path to robottelo dir}/robottelo.properties:/robottelo/robottelo.properties satelliteqe/robottelo <test command>

You can also mount the entire robottelo directory to include the properties file
and any new tests you have written.::

$ docker run -it -v {path to robottelo dir}:/robottelo satelliteqe/robottelo /bin/bash

**Notes:**

- CLI tests run easiest if you include the root credentials in server.yaml
- UI tests should be configured to run through your SauceLabs account.

Running the Tests
=================

Before running any tests, you must create a configuration file::

$ cp virtwho.properties.sample ./virtwho.properties
$ vi virtwho.properties
$ cd conf
$ cp broker.yaml.template ./broker.yaml
$ vi broker.yaml
$ cp robottelo.yaml.template ./robottelo.yaml
$ vi robottelo.yaml
$ cp server.yaml.template ./server.yaml
$ vi server.yaml


That done, you can run tests using ``make``::

$ make test-robottelo
$ make test-docstrings
$ make test-foreman-api
$ make test-foreman-cli
$ make test-foreman-ui
$ make test-foreman-smoke

Robottelo provides two test suites, one for testing Robottelo itself and
another for testing Foreman/Satellite 6. Robottelo's tests are under the
tests/robottelo directory and the Foreman/Satellite 6 tests are under the
tests/foreman directory.

If you want to run tests without the aid of ``make``, you can do that with
either `pytest`_ , `unittest`_ or `nose`_. Just specify the path for the test suite you
want to run::

$ pytest tests/robottelo
$ pytest tests/foreman
$ python -m unittest discover -s tests/robottelo -t .
$ python -m unittest discover -s tests/foreman -t .
$ nosetests tests/robottelo
$ nosetests tests/foreman

The following sections discuss, in detail, how to update the configuration file
and run tests directly.

Initial Configuration
---------------------

To configure Robottelo, multiple template yaml files are present to execute different test cases in Robottelo.
1. server.yaml : Populate server.yaml with ssh credentials and ssh key path. Then, edit the configuration file so that
at least the following attributes are set::
HOSTNAMES=[LIST OF FULLY QUALIFIED DOMAIN NAMES OR IP ADDRESSES]
SSH_USERNAME=[SSH USERNAME]
SSH_PASSWORD=[SSH PASSWORD] / SSH_KEY=[PATH TO YOUR SSH KEY] / SSH_KEY_STRING = [SSH KEY AS STRING]


Note that you only need to configure the SSH key if you want to run CLI tests.
There are other settings to configure what web browser to use for UI tests and
even configuration to run the automation using `SauceLabs`_. For more
information about what web browsers you can use, check Selenium's `WebDriver`_
documentation.

Using environment variables
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Each of the sections in the ``robottelo.properties`` file can be mapped to an
environment variable prefixed with ``ROBOTTELO_`` so for example if you want
to override the ``server.hostname`` without changing the properties file you can do::

$ export ROBOTTELO_SERVER_HOSTNAME=other.hostname.com

The envars follows the format ``ROBOTTELO_{SECTION}_{VALUE}`` all uppercase, more examples::

$ export ROBOTTELO_SERVER_SSH_KEY=path/to/your/key

Using Secrets from Vault
^^^^^^^^^^^^^^^^^^^^^^^^

Robottelo is enabled to fetch secrets from Hashicorp Vault via DynaConf at runtime.

To enable the integration:

#. Copy .env.example to .env file for dynaconf settings object to connect with vault
#. Set VAULT_ENABLED_FOR_DYNACONF to true to enable vault integration
#. Set right values for VAULT_URL_FOR_DYNACONF, VAULT_MOUNT_POINT_FOR_DYNACONF and VAULT_PATH_FOR_DYNACONF
#. Run 'make vault-login' to login into vault and to generate and set the OIDC token automatically
#. Edit any conf file from conf/ directory and add the value for setting in as ``@format {this._secret_name_in_vault_}``.

Running the UI Tests in headless mode
---------------------------------------

You can run browser for UI tests in headless mode by setting browser option in
``robottelo.properties`` file. Currently it is supported only for chrome

browseroptions=headless

Testing With Pytest
---------------------

To run all tests::

$ pytest

It is possible to run a specific subset of tests::

$ pytest test_case.py
$ pytest test_case.py::TestClass
$ pytest test_case.py::TestClass::test_case_name

To get more verbose output, or run multiple tests::

$ pytest tests/ -v
$ pytest tests/robottelo/test_decorators.py tests/robottelo/test_cli.py

To test The Foreman's API, CLI or UI, use the following commands respectively::

$ pytest tests/foreman/api/
$ pytest tests/foreman/cli/
$ pytest tests/foreman/ui/

To collect from three directories in one run::

$ pytest tests/foreman/{cli,api,ui}/test_host.py

To search in testcase names, in this case it will run just negative tests::

$ pytest tests/foreman/cli/test_host.py -k negative

To run tests in several threads, in this case 4::

$ pytest tests/foreman/cli/test_host.py -n 4

For more information about Python's `pytest`_ module, read the documentation.


Running UI Tests On a Docker Browser
------------------------------------

It is possible to run UI tests within a docker container. To do this:

* Install docker. It is provided by the ``docker`` package on Fedora and Red Hat. Be aware that the package may call ``docker-io`` on old OS releases.
* Make sure that docker is running and your user has permission to run docker. For more information, check https://docs.docker.com/engine/installation/.
* Pull the ``selenium/standalone-firefox`` image
* Set ``browser=docker`` in ``conf/robottelo.yaml``


Once you've performed these steps, UI tests will no longer launch a web browser
on your system. Instead, UI tests launch a web browser within a docker
container.


Running UI Tests On a local Docker Browser grid

.. code-block:: shell

    $ . selenium_grid.sh
    $ selenium_grid_start_hub
    Running selenium hub:
    bbaafb2341aae77c32408d1f44e47bed5ced8a97683689b1083080f0389e025c
    $ selenium_grid_start_node
    Running selenium node:
    0d70919ee049679e6dae2cfa7e14d97d26e5be12ad6e48d9a0d1638618f39769
    $ selenium_grid_start_node
    Running selenium node:
    069a294f43be182635008cfdcb6291c8c8cfed4a054640773bfea9a0baae4dc6
    $ selenium_grid_start_node
    Running selenium node:
    4b1881e5d880d49f5380cc90f9ff5deb133c7f42d3565eccb0d91fff6a440307
    $ selenium_grid_start_node
    Running selenium node:
    2504bbe723f3b850b2d87760b7fd90940abb9e827762298652cb5d9facc9195c

We can check the containers started fine:

.. code-block:: shell

    $ podman ps -a | grep selenium-
    bbaafb2341aa  docker.io/selenium/hub:4.3.0                                                /opt/bin/entry_po...  33 seconds ago  Up 33 seconds ago          0.0.0.0:4442-4445->4442-4445/tcp  selenium-hub
    0d70919ee049  docker.io/selenium/node-chrome:4.3.0                                        /opt/bin/entry_po...  30 seconds ago  Up 30 seconds ago                                            selenium-node-chrome-f4qVX
    069a294f43be  docker.io/selenium/node-chrome:4.3.0                                        /opt/bin/entry_po...  28 seconds ago  Up 28 seconds ago                                            selenium-node-chrome-3k56l
    4b1881e5d880  docker.io/selenium/node-chrome:4.3.0                                        /opt/bin/entry_po...  26 seconds ago  Up 26 seconds ago                                            selenium-node-chrome-KIAOk
    2504bbe723f3  docker.io/selenium/node-chrome:4.3.0                                        /opt/bin/entry_po...  24 seconds ago  Up 24 seconds ago                                            selenium-node-chrome-JQhOi
    $ xdg-open http://localhost:4444/ui

To cleanup after the test there is a command

.. code-block:: shell

    selenium_grid_cleanup


Running UI Tests On SauceLabs
-----------------------------

It is possible to run UI tests on SauceLabs. To do this:

* Set ``browser=saucelabs`` in ``conf/robottelo.yaml``.
* Select the browser type by setting ``webdriver`` in ``conf/robottelo.yaml`` section in the configuration file. Valid values are ``firefox``, ``chrome`` and ``ie``.
* Fill ``saucelabs_user`` and ``saucelabs_key`` in ``conf/robottelo.yaml`` section in the configuration file with your Sauce OnDemand credentials.
* If the machine where Satellite 6 is installed is on a VPN or behind a firewall make sure to have SauceConnect running.

Miscellany
==========

.. toctree::
    :hidden:

    committing
    code_standards
    reviewing_PRs
    features/index
    autoapi/index

Want to contribute? Before submitting code, read through the :doc:`committing
guide </committing>` and **Robottelo** :doc:`code standards </code_standards>`.
Ready to start reviewing pull requests? We have :doc:`a guide </reviewing_PRs>`
for that too! Finally, the :doc:`API reference </autoapi/index>` covers
individual functions, classes, methods and modules.

**Robottelo** is compatible with Python 3.6+.

Bugs are listed `on GitHub <https://github.com/SatelliteQE/robottelo/issues>`_.
If you think you've found a new issue, please do one of the following:

* Open a new bug report on Github.
* Join the #robottelo IRC channel on Freenode (irc.freenode.net).

You can generate the documentation for Robottelo as follows, so long as you have
`Sphinx`_ and make installed::

$ cd docs
$ make html

You can generate a graph of Foreman entities and their dependencies, so long as
you have `graphviz`_ installed::

$ make graph-entities

To check for code smells::

$ pre-commit install-hooks
$ pre-commit run --all-files

The design and development for this software is led by `Og Maciel`_.

.. _data driven: http://en.wikipedia.org/wiki/Data-driven_testing
.. _dockerhub: https://hub.docker.com/r/satelliteqe/robottelo/
.. _subTest: https://docs.python.org/3/library/unittest.html#unittest.TestCase.subTest
.. _graphviz: http://graphviz.org/
.. _nose: https://nose.readthedocs.org/en/latest/index.html
.. _Og Maciel: http://www.ogmaciel.com
.. _ssh2-python: https://pypi.org/project/ssh2-python/
.. _Pytest: https://docs.pytest.org/en/latest/contents.html
.. _Requests: http://docs.python-requests.org/en/latest/
.. _Robottelo: https://github.com/SatelliteQE/robottelo
.. _SauceLabs: https://saucelabs.com/
.. _Sphinx: http://sphinx-doc.org/index.html
.. _The Foreman: http://theforeman.org/
.. _unittest: http://docs.python.org/2/library/unittest.html
.. _WebDriver: http://docs.seleniumhq.org/projects/webdriver/
