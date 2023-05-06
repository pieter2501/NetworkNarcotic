# NetworkNarcotic
A tool for automatically plotting networks in GNS3 based on text input.

Reading this README will allow you to perfectly understand and use NetworkNarcotic.

## Description
Current procedure on how to use NetworkNarcotic:
1) Manually build the input .yaml file
2) Feed this input file to the NetworkNarcotic engine (Python script)
    * The engine applies its algorithm against the input file:
        * checking for syntax errors,
        * checking for logic errors,
        * building the network topology in memory,
        * serializing this network topology into a .gns3 project file,
        * and producing an Ansible inventory file for the entire network (TODO).

In the end, you will have a usable network in GNS3. Automatic IP configuration is currently not implemented yet because it requires editing the configuration of the actual devices, not just the .gns3 project file. The router image used is **[c2600-adventerprisek9-mz.124-15.T14.image](https://gns3.com/marketplace/appliances/cisco-2600)**. Somehow editing the default configuration present in this image file would solve the issue, but since Cisco software is closed-source, the code is not accessible. If it were, perhaps after decompiling in Ghidra, NetworkNarcotic could simply clone the image contents per desired router and update the configuration accordingly.

## Expectations
The core idea behind NetworkNarcotic is to **save time** when plotting networks. Input files are relatively straightforward and writing them can be learned quickly. However, since nothing can (as of yet) truly substitute for human intelligence, NetworkNarcotic must make some assumptions about the network you desire. Any 'gaps' in the information you provide, the tool will try to fill in on its own. These decisions are made in a systematic and predictable manner, but in the end, remain out of reach for the user. 

**In automation, there is always a balance between precision and the amount of time saved.**

## Example input file
```
---
input:
  connections:
    - tag: conn_A
      connectionmode: full
      cables: 2

    - tag: conn_B
      connectionmode: parallel

    - tag: conn_C
      switches:
        tag: swit_A
        amount: 4
        clustermode: hubspoke

  routers:
    - tag: rout_A
      gateway: true
      connectedto:
        - conn_A

    - tag: rout_B
      amount: 2
      connectedto:
        - conn_A
        - conn_B
        - conn_C

    - tag: rout_C
      amount: 4
      clustermode: line
      connectionshift: 1
      connectedto:
        - conn_B

    - tag: rout_D
      connectedto:
        - conn_C
```

![The network produced based on the input file above](./img/example.PNG)

As seen in the picture,
* encircled red are router clusters,
* encircled green is a switch cluster in connection 'C'.

Note that by default, the generated topology is based on the Fruchterman Reingold algorithm. The picture above has been manually reorganised to better display the cluster mechanism.

## How to write input files
### **Important before you continue**
NetworkNarcotic input files work with a concept called _clusters_. A cluster is simply a unit of one or more devices. In the example input file up above, you can find 4 router clusters and 1 switch cluster. Clusters and where to find them in an input file:

- Router clusters reside in the **routers** variable.
- Switch clusters reside in a connection definition of the **connections** variable.

You can use a connection if you want to connect clusters to each other or connect a stub network to a router. These connections can be direct (one-to-one) or contain switches, in which case a switch cluster needs to be added inside the desired connection definition. If more than 2 router clusters need to be connected, the connection definition should contain a switch cluster. Only one switch cluster can be added per connection definition.

The way clusters and connections are cabled depends on the variables **clustermode** and **connectionmode**. They're similar but cannot be used interchangeably. If no clustermode variable is defined in a cluster, the default value will be used (in this case 'full'). The same mechanism applies to the connectionmode variable, among others.

Lastly, it's important to know that every device in a cluster (whether router or switch) receives a linearly assigned ID upon creation. Refer to the example network up above to see the ID's as the device name suffix. A cluster with 5 devices has ID's 1 to 5. ID's are unique within a cluster and are used by the **connectionmode** variable to:

* decide which device to select,
* or to break ties when devices get selected in some other way. 

ID = 1 has the highest priority and will always be selected first. Connectionmode values that require device ID's are marked down below with an **\* asterisk**.

### **Variables: YAML structure**

```
---
input:
   connections:
      - tag: ...
        cables: ...
        connectionmode: ...
        shiftable: ...
        switches:
          tag: ...
          amount: ...
          cables: ...
          clustermode: ...
          connectionshift: ...
   routers:
      - tag: ...
        amount: ...
        cables: ...
        clustermode: ...
        connectedto:
          - ...
        connectionshift: ...
        gateway: ...
```

### **Variables: values**

> **input:**

    The global object that defines the input file. Cannot be omitted.

> **amount:** <**1** (default) | number between 1 and 255>

    Influences the amount of devices in a cluster.

> **cables:** <**1** (default) | number between 1 and 3>

    Influences the Etherchannel/Port Channel configuration in a cluster or connection.

> **clustermode:** <**full** (default) | **loop** | **line** | **hubspoke**>

    Influences the cable layout of a cluster.

    > full        full mesh topology, every device is connected to every other device
    > loop        loop topology, devices are connected in a loop
    > line        line topology, basically loop mode with a cut in it
    > hubspoke    hub-and-spoke topology, every device is connected to one central device (ID = 1)
    > ...         (more to come)

> **connections:**

    Opens a connections variable which contains connection definitions.

> **connectionmode:** <**single** (default) | **full** | **parallel**>

    Influences the cable layout of a connection.

    > single *    a single cable is applied between ONE device from each cluster
    > full        every device in one cluster is connected to every device in the other cluster
    > parallel *  multiple cables are applied between parallels of devices from all clusters 
                  until the smallest cluster is exhausted
    > ...         (more to come)

> **connectionshift:** <**0** (default) | number between 0 and 255>

    Influences the starting point of a connection's cabling algorithm for a cluster. With 
    connectionmode = full, the connectionshift variable has no visible effect. This variable has a 
    circular nature and overflow will start back at the device with ID = 1.

> **gateway:** <**false** (default) | **true**>

    Influences whether or not a router cluster is hooked to the escape network, that is,
    the network that provides your own system with internet access. Only router with 
    ID = 1 acts as a gateway.

> **routers:**

    Opens a routers variable which contains router cluster definitions.

> **shiftable:** <**true** (default) | **false**>

    Influences whether or not a connection is susceptible to the connectionshift variable when 
    connected to a cluster.

> **switches:**

     Opens a switches variable which contains switch cluster definitions. This is always done 
     inside a connection definition. This variable cannot be combined with an internet variable 
     in the same connection.
