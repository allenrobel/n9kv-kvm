# This file is meant to be sourced.
# e.g. source ./evn_ansible.sh
export ANSIBLE_HOME=$HOME/repos/ansible
export ANSIBLE_COLLECTIONS_PATH=$HOME/repos/ansible/collections
export ANSIBLE_DEV_HOME=$ANSIBLE_COLLECTIONS_PATH/ansible_collections/ansible
export ANSIBLE_CISCO_PATH=$ANSIBLE_COLLECTIONS_PATH/ansible_collections/cisco
export ANSIBLE_DCNM_PATH=$ANSIBLE_CISCO_PATH/dcnm
export ANSIBLE_ND_PATH=$ANSIBLE_CISCO_PATH/nd
export ANSIBLE_ROLES_PATH=$ANSIBLE_DCNM_PATH/tests/integration/targets
export ANSIBLE_PERSISTENT_COMMAND_TIMEOUT=1200
export ANSIBLE_PERSISTENT_CONNECT_TIMEOUT=1200
export ND_FABRIC_ISN=ISN
export ND_FABRIC_MSD=MSD
export ND_FABRIC_SITE1=SITE1
export ND_FABRIC_SITE2=SITE2
export ND_IP4=192.168.7.7
export ND_PASSWORD=SecretPassword
export ND_USERNAME=admin
