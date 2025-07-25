# This file is meant to be sourced.
# e.g. source ./evn_ansible.sh
export ANSIBLE_HOME=$HOME/repos/ansible
export ANSIBLE_COLLECTIONS_PATH=$HOME/repos/ansible/collections
export ANSIBLE_DEV_HOME=$HOME/repos/ansible/collections/ansible_collections/ansible
export ANSIBLE_ROLES_PATH=$ANSIBLE_COLLECTIONS_PATH/ansible_collections/cisco/dcnm/tests/integration/targets
export ANSIBLE_PERSISTENT_COMMAND_TIMEOUT=1200
export ANSIBLE_PERSISTENT_CONNECT_TIMEOUT=1200
export ND_FABRIC_VXLAN=f1
export ND_FABRIC_ISN=ISN
export ND_IP4=192.168.1.2
export ND_PASSWORD=SecretPassword
export ND_USERNAME=admin
