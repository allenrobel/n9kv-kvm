# Install the Nexus Dashboard Fabric Controller Ansible Collection

We'll need to run some playbooks to fix mac address issues with nexus9000v.  These playbooks
require the NDFC Ansible Collection (aka the DCNM Ansible Collection).

This collection provides modules to interact with ND's REST API to build fabrics, manage inventory, create VRFs
and Networks, etc.  It also provides a policy module, which we'll use later to push configuration policies to the
ND controller.

## Define Required Environment Variables

The environment variables below tell `ansible-galaxy` where to install the collection.

```bash
export ANSIBLE_HOME=$HOME/repos/ansible
export ANSIBLE_COLLECTIONS_PATH=$HOME/repos/ansible/collections
```

## Create the Directory Structure

Below we create the directory structure, matching the above environment variables,
to hold our Ansible collection.

```bash
mkdir $HOME/repos/ansible/collections
mkdir $HOME/repos/ansible/collections/ansible_collections
mkdir $HOME/repos/ansible/collections/ansible_collections/cisco
```

## Install the Collection

Now we'll use `ansible-galaxy` to install this collection.

One gotcha.  Make sure that the virtual environment for the n9kv-env repository is listed first in your PYTHONPATH .
If it's not, then potentially random versions of urllib3 might be used, which can cause certificate errors when using
ansible-galaxy, as shown below.

```bash
[WARNING]: Skipping Galaxy server https://galaxy.ansible.com. Got an unexpected error when getting available versions of collection
cisco.dcnm: Unknown error when attempting to call Galaxy at 'https://galaxy.ansible.com/api/': HTTPSConnection.__init__() got an
unexpected keyword argument 'cert_file'
ERROR! Unknown error when attempting to call Galaxy at 'https://galaxy.ansible.com/api/': HTTPSConnection.__init__() got an unexpected keyword argument 'cert_file'
```

Below we:

- Activate the virtual environment
- Set the `PYTHONPATH` to include only the virtual environment
- Verify that `ansible-galaxy` is where we expect it to be

```bash
arobel@cvd-3:~$ source $HOME/repos/n9kv-kvm/.venv/bin/activate
arobel@cvd-3:~$ export PYTHONPATH=$HOME/repos/n9kv-kvm/.venv
(.venv) arobel@cvd-3:~$ which ansible-galaxy
/home/arobel/repos/n9kv-kvm/.venv/bin/ansible-galaxy
(.venv) arobel@cvd-3:~$ 
```

Now let's install the collection.

```bash
(.venv) arobel@cvd-3:~$ ansible-galaxy collection install cisco.dcnm
Starting galaxy collection install process
Process install dependency map
Starting collection install process
Downloading https://galaxy.ansible.com/api/v3/plugin/ansible/content/published/collections/artifacts/cisco-dcnm-3.8.1.tar.gz to /home/arobel/repos/ansible/tmp/ansible-local-23568qgteb88r/tmp6nisrlrk/cisco-dcnm-3.8.1-idxyz0e1
Installing 'cisco.dcnm:3.8.1' to '/home/arobel/repos/ansible/collections/ansible_collections/cisco/dcnm'
cisco.dcnm:3.8.1 was installed successfully
'ansible.netcommon:7.2.0' is already installed, skipping.
'ansible.utils:5.1.2' is already installed, skipping.
(.venv) arobel@cvd-3:~$
```

## Verify the Collection is Installed

```bash
(.venv) arobel@cvd-3:~$ ls -l $ANSIBLE_COLLECTIONS_PATH/ansible_collections/cisco/dcnm
total 320
-rw-r--r-- 1 arobel arobel  18977 Jul 29 19:00 CHANGELOG.rst
-rw-r--r-- 1 arobel arobel      0 Jul 29 19:00 dcnm-ut
drwxr-xr-x 2 arobel arobel   4096 Jul 29 19:00 docs
-rw-r--r-- 1 arobel arobel 244905 Jul 29 19:00 FILES.json
-rw-r--r-- 1 arobel arobel      0 Jul 29 19:00 __init__.py
-rw-r--r-- 1 arobel arobel  11361 Jul 29 19:00 LICENSE
-rw-r--r-- 1 arobel arobel   1057 Jul 29 19:00 MANIFEST.json
drwxr-xr-x 2 arobel arobel   4096 Jul 29 19:00 meta
drwxr-xr-x 4 arobel arobel   4096 Jul 29 19:00 playbooks
drwxr-xr-x 6 arobel arobel   4096 Jul 29 19:00 plugins
-rw-r--r-- 1 arobel arobel  10127 Jul 29 19:00 README.md
-rw-r--r-- 1 arobel arobel     17 Jul 29 19:00 requirements.txt
-rw-r--r-- 1 arobel arobel    124 Jul 29 19:00 test-requirements.txt
drwxr-xr-x 5 arobel arobel   4096 Jul 29 19:00 tests
-rw-r--r-- 1 arobel arobel    639 Jul 29 19:00 tox.ini
(.venv) arobel@cvd-3:~$ 
```
