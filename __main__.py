import base64
from pulumi import Config, Output, export
import pulumi_azure_native.compute as compute
import pulumi_azure_native.network as network
import pulumi_azure_native.resources as resources

# variables
prefix = "vmg"

config = Config()
username = config.require("username")
password = config.require("password")

resource_group = resources.ResourceGroup(prefix+"-server")

nsg = network.NetworkSecurityGroup(
    resource_name=prefix+"-nsg",
    location = resource_group.location,
    resource_group_name = resource_group.name,
    security_rules=[network.SecurityRuleArgs(
        name="allow8443",
        priority=100,
        direction="Inbound",
        access="Allow",
        protocol="Tcp",
        source_port_range="*",
        destination_port_range="8443",
        source_address_prefix="99.225.126.159",
        destination_address_prefix="*"),
    network.SecurityRuleArgs(
        name="allow22",
        priority=101,
        direction="Inbound",
        access="Allow",
        protocol="Tcp",
        source_port_range="*",
        destination_port_range="22",
        source_address_prefix="99.225.126.159",
        destination_address_prefix="*"),
    network.SecurityRuleArgs(
        name="denyall",
        priority=102,
        direction="Inbound",
        access="Deny",
        protocol="*",
        source_port_range="*",
        destination_port_range="*",
        source_address_prefix="*",
        destination_address_prefix="*"),
    ]
)

net = network.VirtualNetwork(
    prefix+"-vnet",
    resource_group_name=resource_group.name,
    address_space=network.AddressSpaceArgs(
        address_prefixes=["10.0.0.0/16"],
    ),
    subnets=[network.SubnetArgs(
        name=prefix+"-subnet",
        address_prefix="10.0.1.0/24",
        network_security_group=network.NetworkSecurityGroupArgs(
            id = nsg.id
        )
    )])

public_ip = network.PublicIPAddress(
    prefix+"-vm-pub-ip",
    resource_group_name=resource_group.name,
    public_ip_allocation_method=network.IPAllocationMethod.DYNAMIC)

network_iface = network.NetworkInterface(
    prefix+"-vm-nic",
    resource_group_name=resource_group.name,
    ip_configurations=[network.NetworkInterfaceIPConfigurationArgs(
        name="webserveripcfg",
        subnet=network.SubnetArgs(id=net.subnets[0].id),
        private_ip_allocation_method=network.IPAllocationMethod.DYNAMIC,
        public_ip_address=network.PublicIPAddressArgs(id=public_ip.id),
    )])

init_script = """#!/bin/bash
sudo apt-get update
sudo apt-get install -y \
  ca-certificates \
  curl \
  gnupg \
  lsb-release
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose
cd /home/azureuser
git clone https://github.com/f5devcentral/f5-journeys.git
cd f5-journeys
cp sample.env .env
sed -i 's/"127.0.0.1:${JOURNEYS_PORT}:443"/"${JOURNEYS_PORT}:443"/' docker-compose.yaml
docker-compose pull
docker-compose up -d"""

vm = compute.VirtualMachine(
    prefix+"-server-vm",
    resource_group_name=resource_group.name,
    network_profile=compute.NetworkProfileArgs(
        network_interfaces=[
            compute.NetworkInterfaceReferenceArgs(id=network_iface.id),
        ],
    ),
    hardware_profile=compute.HardwareProfileArgs(
        vm_size="Standard_D8_v3",
    ),
    os_profile=compute.OSProfileArgs(
        computer_name="ubuntu18",
        admin_username=username,
        admin_password=password,
        custom_data=base64.b64encode(init_script.encode("ascii")).decode("ascii"),
        linux_configuration=compute.LinuxConfigurationArgs(
            disable_password_authentication=False,
        ),
    ),
    storage_profile=compute.StorageProfileArgs(
        os_disk=compute.OSDiskArgs(
            create_option=compute.DiskCreateOptionTypes.FROM_IMAGE,
            name="myosdisk1",
        ),
        image_reference=compute.ImageReferenceArgs(
            publisher="canonical",
            offer="UbuntuServer",
            sku="18.04-LTS",
            version="latest",
        ),
    ))

public_ip_addr = vm.id.apply(lambda _: network.get_public_ip_address_output(
    public_ip_address_name=public_ip.name,
    resource_group_name=resource_group.name))

export("public_ip", public_ip_addr.ip_address)