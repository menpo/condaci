CondaCI - A Continuous Integration Conda management script
==========================================================

CondaCI (Continuous Integration) is a bootstrapping Python script for
automatic Conda deployments from TravisCI and AppVeyor. CondaCI handles:

- The downloading and installation of a fresh up-to-date version of miniconda
- Configuration of Conda installation files
- The running of conda build
- The deployment of passing builds to binstar
