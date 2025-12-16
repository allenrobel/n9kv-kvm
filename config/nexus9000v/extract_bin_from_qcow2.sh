#!/usr/bin/env bash
NXOS_VERSION=10.6.2.F
NXOS_QCOW2_DIR=/iso1/nxos/qcow2
NXOS_BIN_DIR=/iso1/nxos/bin

NXOS_QCOW2=nexus9300v64.$NXOS_VERSION.qcow2
NXOS_BIN=nxos64-cs.$NXOS_VERSION.bin
mkdir -p $NXOS_QCOW2_DIR
mkdir -p $NXOS_BIN_DIR
cd $NXOS_QCOW2_DIR

cd $NXOS_BIN_DIR
sudo guestfish -a $NXOS_QCOW2_DIR/$NXOS_QCOW2 -m /dev/sda4 ls /
sudo guestfish -a $NXOS_QCOW2_DIR/$NXOS_QCOW2 -m /dev/sda4 copy-out  /$NXOS_BIN $NXOS_BIN_DIR