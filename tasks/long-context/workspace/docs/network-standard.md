# Nordlake Compute Platform: Site Network and Node Addressing Standard

Document ID: NCP-NET-STD-004. Revision 14. Status: approved. Owner: Platform Network Engineering. Approvers: Platform Architecture Board. Classification: internal.

This standard is the single source for the physical network, the address plan and the naming of the nodes of the Nordlake Compute Platform. Tools that compute names, addresses, VLANs or interface settings for nodes must agree with the current revision of this document. If a tool and this document do not agree, the document is correct and the tool must be changed.

## Contents

1. Scope and terms
2. Sites
3. Rack layout
4. Host names
5. IPv4 address plan
6. Out-of-band management network
7. In-band management network
8. BMC configuration
9. Switch fabric
10. Routing
11. Interface settings
12. Cabling and link aggregation
13. VLAN plan
14. DNS
15. Time synchronisation
16. Provisioning
17. Storage fabric
18. Security zones
19. Site deviations
20. Monitoring
21. Change control
22. Appendix A: Lessons learned
23. Appendix B: Design decisions
24. Appendix C: Leaf switch inventory
25. Appendix D: Revision history

## 1. Scope and terms

**R-1.1** This standard applies to all sites of the Nordlake Compute Platform that table 2-1 lists, and to all nodes, switches, PDUs and console servers in those sites. Lab equipment in the office networks is out of scope.

**R-1.2** The words "must" and "must not" state a requirement. The word "should" states a recommendation: a deviation from a recommendation needs a reason in the change record, but no approval.

**R-1.3** Rules have the form R-<section>.<number>. A rule number is never used again for a different rule. A withdrawn rule stays in the document with the mark "withdrawn", so that old references stay valid.

**R-1.4** Section 19 lists the approved site deviations. A deviation takes precedence over the general rule that it names. Tools that compute addresses, VLANs or interface settings must implement the deviations as well as the general rules.

**R-1.5** Requests for a change of this standard go to the Platform Network Engineering backlog. Section 21 describes the change process.

Terms used in this standard:

| Term | Meaning |
|---|---|
| BMC | Baseboard management controller of a node. Also called the out-of-band controller. |
| OOB | Out-of-band. The OOB network connects BMCs, PDUs, console servers and switch management ports. |
| In-band management | The network that the node operating system uses for SSH, configuration management and monitoring. |
| Data network | The network for workload traffic between nodes and to the site border. |
| Storage network | The network between nodes and the storage systems (Ceph and NFS gateways). |
| Leaf | A top-of-rack switch of the data and storage fabric. |
| Spine | An aggregation switch of the data and storage fabric of a site. |
| Hall | A data hall of a site. Most sites have one hall, A. |
| Rack number | The number of a rack in its site, 1 to the highest rack number in table 2-1. Rack numbers do not restart in a new hall. |
| Slot | The lowest rack unit that a node occupies, 1 (bottom) to 42 (top). |
| Site octet | The number in table 2-1 that identifies a site in IPv4 addresses. |
| Node | A server that runs workload or platform services. Switches, PDUs and console servers are not nodes. |

## 2. Sites

**R-2.1** Each site has a four-character code: three letters for the city and one digit. Codes are written in upper case in documents and in lower case in host names and DNS names.

**R-2.2** Table 2-1 is the list of sites. The site octet of a site never changes, also when a site is closed.

Table 2-1: Sites

| Code | City | Data centre | Site octet | Halls | Racks | In service since |
|---|---|---|---|---|---|---|
| HEL1 | Helsinki | Kilo DC, building 2 | 16 | A | 1 to 48 | 2019 |
| HEL2 | Vantaa | Vantaa Campus, building V3 | 17 | A (racks 1 to 40), B (racks 41 to 64) | 1 to 64 | 2022 |
| OUL1 | Oulu | Oulu Arctic DC | 24 | A, storage hall S | 1 to 32 | 2021 |
| TMP1 | Tampere | Hervanta DC | 32 | A | 1 to 24 | 2020 |
| ESP1 | Espoo | Otaniemi colocation, suite 4 | 40 | A | 1 to 36 | 2023 |

**R-2.3** Site octets 0 to 15 and 48 to 63 are reserved for future sites. The octets 64 to 127 belong to the in-band management and data address ranges (section 5) and are never site octets.

**R-2.4** A new site gets the next free site octet that is a multiple of 8, unless the Platform Architecture Board decides otherwise.

### 2.1. HEL1, Helsinki

HEL1 is in Kilo DC, building 2 in Helsinki. The site has been in service since 2019. It has one hall, A, with the racks 1 to 48. The contracted IT power is 2.4 MW with two feeds from different substations. Cooling is a mix of rear-door heat exchangers and in-row units. Remote hands requests go through the provider portal and need a ticket number of the platform team.

Notable events at this site, for the context of some rules in this standard:

- 2026: an incorrect VLAN on a leaf port connected 25 nodes to the wrong storage network for one day.
- 2019: a power test of the facility opened the breakers of feed B for 19 seconds; all racks stayed up on feed A.
- 2019: a cooling unit failed during a heat wave and the site team shut down 13 GPU nodes to keep the inlet temperature below the limit.
- 2023: a firmware bug in the OOB switches stopped the BMC access of 3 racks until the switches were restarted.

Connectivity of HEL1: two 400 Gbit/s links on dark fibre, one to each of the two nearest sites, and two internet transits of 100 Gbit/s from different carriers. The inter-site links carry the replication of the platform services, the central logging and the backup traffic. Tenant traffic between sites uses the overlay and is limited to the bandwidth that the tenant contract gives.

Access to HEL1: the provider gives badge access to the persons on the access list of the platform team. The list is reviewed every quarter. Photography in the data halls is not allowed, except for the documentation of a rack during an audit.

### 2.2. HEL2, Vantaa

HEL2 is in Vantaa Campus, building V3 in Vantaa. The site has been in service since 2022. Its halls are A (racks 1 to 40), B (racks 41 to 64). The racks are numbered 1 to 64 over all halls. The contracted IT power is 3.2 MW with one 20 kV feed and a diesel backup. The platform team operates the cooling plant together with the facility team of the owner. Remote hands requests go through the provider portal and need a ticket number of the platform team.

Notable events at this site, for the context of some rules in this standard:

- 2023: a PDU firmware update restarted the PDU management cards of 16 racks; the power to the nodes was not interrupted.
- 2025: a power test of the facility opened the breakers of feed B for 5 seconds; all racks stayed up on feed A.
- 2023: a cooling unit failed during a heat wave and the site team shut down 22 GPU nodes to keep the inlet temperature below the limit.
- 2025: the site doubled its GPU capacity in 2 weeks with a temporary provisioning network.

Connectivity of HEL2: two 400 Gbit/s links on dark fibre, one to each of the two nearest sites, and two internet transits of 100 Gbit/s from different carriers. The inter-site links carry the replication of the platform services, the central logging and the backup traffic. Tenant traffic between sites uses the overlay and is limited to the bandwidth that the tenant contract gives.

Access to HEL2: named persons of the site team have badge access. Other persons need an escort and a visit request two working days before the visit. Photography in the data halls is not allowed, except for the documentation of a rack during an audit.

### 2.3. OUL1, Oulu

OUL1 is in Oulu Arctic DC in Oulu. The site has been in service since 2021. Its halls are A, storage hall S. The racks are numbered 1 to 32 over all halls. The contracted IT power is 1.6 MW with two feeds from different substations. The platform team operates the cooling plant together with the facility team of the owner. The remote hands service is available 24 hours, 7 days a week.

Notable events at this site, for the context of some rules in this standard:

- 2024: a power test of the facility opened the breakers of feed B for 16 seconds; all racks stayed up on feed A.
- 2025: the provider moved the meet-me room, and the border links were down for 21 minutes in a planned window.
- 2021: a fibre cut on the campus ring isolated the site from the central services for 16 minutes.
- 2023: an incorrect VLAN on a leaf port connected 3 nodes to the wrong storage network for one day.

Connectivity of OUL1: two diverse fibre paths to the HEL1 and HEL2 border routers, 100 Gbit/s each, plus a 10 Gbit/s internet transit from a second carrier. The inter-site links carry the replication of the platform services, the central logging and the backup traffic. Tenant traffic between sites uses the overlay and is limited to the bandwidth that the tenant contract gives.

Access to OUL1: named persons of the site team have badge access. Other persons need an escort and a visit request two working days before the visit. Photography in the data halls is not allowed, except for the documentation of a rack during an audit.

### 2.4. TMP1, Tampere

TMP1 is in Hervanta DC in Tampere. The site has been in service since 2020. It has one hall, A, with the racks 1 to 24. The contracted IT power is 2.4 MW with two independent 10 kV feeds. The platform team operates the cooling plant together with the facility team of the owner. Remote hands requests go through the provider portal and need a ticket number of the platform team.

Notable events at this site, for the context of some rules in this standard:

- 2026: a leaf pair upgrade failed and the rack was without data network for 38 minutes.
- 2026: a cooling unit failed during a heat wave and the site team shut down 19 GPU nodes to keep the inlet temperature below the limit.
- 2020: the site doubled its GPU capacity in 39 weeks with a temporary provisioning network.
- 2021: an incorrect VLAN on a leaf port connected 40 nodes to the wrong storage network for one day.

Connectivity of TMP1: two diverse fibre paths to the HEL1 and HEL2 border routers, 100 Gbit/s each, plus a 10 Gbit/s internet transit from a second carrier. The inter-site links carry the replication of the platform services, the central logging and the backup traffic. Tenant traffic between sites uses the overlay and is limited to the bandwidth that the tenant contract gives.

Access to TMP1: the site has a man-trap entrance with badge and PIN. Deliveries go to the loading bay and are checked by the provider security. Photography in the data halls is not allowed, except for the documentation of a rack during an audit.

### 2.5. ESP1, Espoo

ESP1 is in Otaniemi colocation, suite 4 in Espoo. The site has been in service since 2023. It has one hall, A, with the racks 1 to 36. The contracted IT power is 2.4 MW with one 20 kV feed and a diesel backup. The platform team operates the cooling plant together with the facility team of the owner. The remote hands service is available 24 hours, 7 days a week.

Notable events at this site, for the context of some rules in this standard:

- 2026: a leaf pair upgrade failed and the rack was without data network for 2 minutes.
- 2025: the site doubled its GPU capacity in 6 weeks with a temporary provisioning network.
- 2026: a firmware bug in the OOB switches stopped the BMC access of 10 racks until the switches were restarted.
- 2026: an incorrect VLAN on a leaf port connected 11 nodes to the wrong storage network for one day.

Connectivity of ESP1: a leased 100 Gbit/s wavelength to HEL1 and a 100 Gbit/s wavelength to HEL2 on a different route, with internet transit through HEL1. The inter-site links carry the replication of the platform services, the central logging and the backup traffic. Tenant traffic between sites uses the overlay and is limited to the bandwidth that the tenant contract gives.

Access to ESP1: the site has a man-trap entrance with badge and PIN. Deliveries go to the loading bay and are checked by the provider security. Photography in the data halls is not allowed, except for the documentation of a rack during an audit.

## 3. Rack layout

**R-3.1** All racks are 42U, 600 mm wide and 1200 mm deep, with front-to-back airflow.

**R-3.2** The out-of-band switch is in U42. The leaf switches are in U40 and U41. U39 is a cable management panel.

**R-3.3** The console server is in U38 in racks that have one (one console server for each four racks, in the rack with the lowest number of the group).

**R-3.4** Nodes fill the rack from U1 upwards. The slot of a node is its lowest rack unit. A 2U node in U5 and U6 has slot 5.

**R-3.5** Each rack has two PDUs, A and B, on different power feeds. Each node connects one power supply to each PDU.

**R-3.6** A rack must not have more than 17 kW of planned load in hall A and 34 kW in rooms with liquid cooling.

**R-3.7** Blanking panels must close all free rack units, also during maintenance that lasts more than one day.

**R-3.8** The rack label shows the site code, the rack number and the hall, for example "HEL1 A 07".

**R-3.9** Cables are routed overhead. Raised floor is used only for cooling.

**R-3.10** A GPU node with liquid cooling occupies 4U and needs a manifold connection at the back of the rack.

Table 3-1 gives the typical node heights. The provisioning team uses it to plan the slots of a new rack.

Table 3-1: Node heights

| Node model | Role | Height | Typical slots |
|---|---|---|---|
| NL-C2 | compute | 1U | 1, 2, 3, 4, 5, 6, ... |
| NL-C4 | compute | 2U | 1, 3, 5, 7, 9, 11, ... |
| NL-G8 | gpu | 4U | 1, 5, 9, 13, 17, 21, ... |
| NL-G4L | gpu | 4U | 1, 5, 9, 13, 17, 21, ... |
| NL-S24 | storage | 2U | 1, 3, 5, 7, 9, 11, ... |
| NL-S60 | storage | 4U | 1, 5, 9, 13, 17, 21, ... |
| NL-M1 | control-plane | 1U | 1, 2, 3, 4, 5, 6, ... |
| NL-I1 | infra | 1U | 1, 2, 3, 4, 5, 6, ... |

**R-3.11** A rack must not contain both liquid-cooled GPU nodes and storage nodes with more than 24 drives, because the weight limit of the floor tiles would be exceeded.

**R-3.12** The planned position of each node is recorded in the inventory system before the node arrives at the site. The rack and the slot in the inventory system are the input of all naming and addressing rules.

This section gives the purpose, the power budget and the cooling of the racks of each site. The site teams update it through a change record (section 21) when the purpose of a rack changes. The purpose limits the roles of the nodes that the provisioning system accepts in a rack: a compute rack accepts compute and infra nodes, a GPU rack accepts GPU nodes, a storage rack accepts storage nodes, and a mixed rack accepts compute and storage nodes.

### 3.1. Racks of HEL1

- Racks 1 and 2 (hall A): infra, 8 kW, air cooling.
- Rack 3 (hall A): compute, 17 kW, rear door cooling.
- Rack 4 (hall A): infra, 17 kW, air cooling.
- Rack 5 (hall A): infra, 17 kW, rear door cooling.
- Rack 6 (hall A): infra, 14 kW, rear door cooling. Nodes from the 2021 purchase, out of vendor support in 2027.
- Rack 7 (hall A): storage, 14 kW, air cooling.
- Rack 8 (hall A): GPU, 17 kW, air cooling.
- Rack 9 (hall A): storage, 10 kW, air cooling. Planned for a refresh in 2027.
- Rack 10 (hall A): infra, 14 kW, air cooling.
- Rack 11 (hall A): GPU, 30 kW, liquid cooling.
- Rack 12 (hall A): compute, 12 kW, rear door cooling.
- Rack 13 (hall A): infra, 12 kW, air cooling.
- Rack 14 (hall A): mixed, 10 kW, air cooling.
- Rack 15 (hall A): infra, 14 kW, air cooling.
- Rack 16 (hall A): compute, 12 kW, air cooling.
- Rack 17 (hall A): compute, 17 kW, air cooling.
- Rack 18 (hall A): infra, 12 kW, air cooling.
- Rack 19 (hall A): mixed, 14 kW, air cooling. The rear door heat exchanger is shared with the next rack.
- Rack 20 (hall A): GPU, 30 kW, liquid cooling.
- Rack 21 (hall A): compute, 12 kW, air cooling.
- Rack 22 (hall A): storage, 17 kW, air cooling.
- Rack 23 (hall A): compute, 10 kW, air cooling.
- Rack 24 (hall A): GPU, 30 kW, liquid cooling. Nodes from the 2021 purchase, out of vendor support in 2027.
- Rack 25 (hall A): mixed, 12 kW, air cooling.
- Rack 26 (hall A): infra, 10 kW, air cooling. Contains loaner nodes of a vendor.
- Rack 27 (hall A): compute, 10 kW, rear door cooling. Contains loaner nodes of a vendor.
- Rack 28 (hall A): infra, 14 kW, air cooling.
- Rack 29 (hall A): compute, 14 kW, air cooling.
- Rack 30 (hall A): mixed, 17 kW, air cooling.
- Rack 31 (hall A): compute, 12 kW, air cooling. The rear door heat exchanger is shared with the next rack.
- Rack 32 (hall A): infra, 17 kW, air cooling.
- Rack 33 (hall A): infra, 10 kW, air cooling.
- Rack 34 (hall A): GPU, 34 kW, liquid cooling.
- Rack 35 (hall A): GPU, 12 kW, air cooling.
- Rack 36 (hall A): GPU, 30 kW, liquid cooling.
- Rack 37 (hall A): storage, 14 kW, air cooling.
- Rack 38 (hall A): compute, 10 kW, air cooling.
- Rack 39 (hall A): compute, 12 kW, air cooling. The rear door heat exchanger is shared with the next rack.
- Rack 40 (hall A): infra, 12 kW, air cooling.
- Rack 41 (hall A): storage, 12 kW, air cooling.
- Rack 42 (hall A): compute, 14 kW, air cooling.
- Rack 43 (hall A): compute, 17 kW, rear door cooling.
- Rack 44 (hall A): infra, 17 kW, rear door cooling.
- Rack 45 (hall A): compute, 10 kW, air cooling.
- Rack 46 (hall A): mixed, 12 kW, rear door cooling. Planned for a refresh in 2027.
- Racks 47 and 48 (hall A): network, 6 kW, air cooling. Contains the console server of the rack group.

### 3.2. Racks of HEL2

- Racks 1 and 2 (hall A): infra, 8 kW, air cooling. Planned for a refresh in 2027.
- Rack 3 (hall A): compute, 10 kW, rear door cooling.
- Rack 4 (hall A): storage, 14 kW, air cooling.
- Rack 5 (hall A): mixed, 12 kW, rear door cooling.
- Rack 6 (hall A): compute, 14 kW, air cooling.
- Rack 7 (hall A): mixed, 12 kW, rear door cooling. Planned for a refresh in 2027.
- Rack 8 (hall A): infra, 14 kW, air cooling.
- Rack 9 (hall A): mixed, 14 kW, air cooling. Planned for a refresh in 2027.
- Rack 10 (hall A): infra, 12 kW, rear door cooling.
- Rack 11 (hall A): compute, 12 kW, air cooling.
- Rack 12 (hall A): infra, 12 kW, air cooling.
- Rack 13 (hall A): storage, 12 kW, air cooling. Half empty because of the power budget.
- Rack 14 (hall A): GPU, 30 kW, liquid cooling.
- Racks 15 and 16 (hall A): storage, 14 kW, air cooling.
- Rack 17 (hall A): infra, 12 kW, air cooling.
- Rack 18 (hall A): compute, 10 kW, air cooling.
- Rack 19 (hall A): compute, 14 kW, air cooling.
- Rack 20 (hall A): compute, 14 kW, rear door cooling.
- Rack 21 (hall A): mixed, 14 kW, air cooling.
- Rack 22 (hall A): infra, 14 kW, air cooling.
- Rack 23 (hall A): GPU, 34 kW, liquid cooling.
- Rack 24 (hall A): infra, 17 kW, air cooling. Planned for a refresh in 2027.
- Rack 25 (hall A): compute, 10 kW, air cooling.
- Rack 26 (hall A): compute, 17 kW, air cooling.
- Rack 27 (hall A): mixed, 12 kW, air cooling.
- Rack 28 (hall A): GPU, 30 kW, liquid cooling. The rear door heat exchanger is shared with the next rack.
- Rack 29 (hall A): compute, 17 kW, air cooling. Half empty because of the power budget.
- Rack 30 (hall A): mixed, 12 kW, rear door cooling.
- Rack 31 (hall A): GPU, 30 kW, liquid cooling.
- Rack 32 (hall A): compute, 12 kW, rear door cooling. Planned for a refresh in 2027.
- Rack 33 (hall A): compute, 14 kW, air cooling.
- Rack 34 (hall A): GPU, 17 kW, air cooling.
- Rack 35 (hall A): GPU, 34 kW, liquid cooling. Power feed b on a temporary circuit until the next facility window.
- Rack 36 (hall A): mixed, 14 kW, rear door cooling.
- Rack 37 (hall A): infra, 14 kW, air cooling.
- Rack 38 (hall A): mixed, 17 kW, air cooling.
- Rack 39 (hall A): mixed, 12 kW, air cooling. Contains the console server of the rack group.
- Rack 40 (hall A): storage, 17 kW, rear door cooling. Contains the console server of the rack group.
- Rack 41 (hall B): GPU, 34 kW, liquid cooling. The rear door heat exchanger is shared with the next rack.
- Rack 42 (hall B): compute, 17 kW, air cooling.
- Rack 43 (hall B): compute, 12 kW, rear door cooling.
- Rack 44 (hall B): mixed, 17 kW, air cooling.
- Rack 45 (hall B): mixed, 14 kW, air cooling.
- Rack 46 (hall B): GPU, 34 kW, liquid cooling. Power feed b on a temporary circuit until the next facility window.
- Rack 47 (hall B): compute, 14 kW, rear door cooling.
- Rack 48 (hall B): compute, 17 kW, air cooling.
- Rack 49 (hall B): infra, 10 kW, air cooling. Contains the console server of the rack group.
- Rack 50 (hall B): compute, 12 kW, air cooling.
- Rack 51 (hall B): mixed, 12 kW, rear door cooling.
- Rack 52 (hall B): GPU, 34 kW, liquid cooling. The rear door heat exchanger is shared with the next rack.
- Rack 53 (hall B): GPU, 14 kW, rear door cooling. Planned for a refresh in 2027.
- Rack 54 (hall B): mixed, 14 kW, air cooling.
- Rack 55 (hall B): GPU, 14 kW, air cooling.
- Rack 56 (hall B): storage, 17 kW, rear door cooling.
- Rack 57 (hall B): storage, 17 kW, air cooling.
- Rack 58 (hall B): compute, 12 kW, rear door cooling.
- Rack 59 (hall B): GPU, 34 kW, liquid cooling.
- Rack 60 (hall B): storage, 14 kW, rear door cooling. Nodes from the 2021 purchase, out of vendor support in 2027.
- Rack 61 (hall B): GPU, 12 kW, air cooling.
- Rack 62 (hall B): infra, 10 kW, rear door cooling.
- Rack 63 (hall B): mixed, 17 kW, air cooling.
- Rack 64 (hall B): compute, 10 kW, air cooling.

### 3.3. Racks of OUL1

- Racks 1 and 2 (hall A): infra, 8 kW, air cooling.
- Rack 3 (hall A): mixed, 12 kW, rear door cooling. Nodes from the 2021 purchase, out of vendor support in 2027.
- Rack 4 (hall A): mixed, 10 kW, rear door cooling.
- Rack 5 (hall A): compute, 10 kW, rear door cooling.
- Rack 6 (hall A): infra, 17 kW, rear door cooling. Half empty because of the power budget.
- Rack 7 (hall A): infra, 10 kW, rear door cooling.
- Rack 8 (hall A): mixed, 14 kW, air cooling.
- Rack 9 (hall A): compute, 10 kW, rear door cooling.
- Rack 10 (hall A): compute, 17 kW, rear door cooling.
- Rack 11 (hall A): mixed, 17 kW, rear door cooling.
- Rack 12 (hall A): compute, 14 kW, air cooling. Contains loaner nodes of a vendor.
- Rack 13 (hall A): compute, 12 kW, air cooling.
- Rack 14 (hall A): storage, 10 kW, air cooling.
- Rack 15 (hall A): mixed, 17 kW, rear door cooling.
- Rack 16 (hall A): GPU, 17 kW, air cooling.
- Rack 17 (hall A): storage, 12 kW, air cooling. The rear door heat exchanger is shared with the next rack.
- Rack 18 (hall A): storage, 17 kW, air cooling. Contains the console server of the rack group.
- Rack 19 (hall A): GPU, 34 kW, liquid cooling.
- Rack 20 (hall A): compute, 14 kW, air cooling.
- Rack 21 (hall A): GPU, 34 kW, liquid cooling. Half empty because of the power budget.
- Rack 22 (hall A): mixed, 17 kW, air cooling.
- Rack 23 (hall A): compute, 17 kW, air cooling.
- Racks 24 to 26 (hall A): GPU, 34 kW, liquid cooling.
- Rack 27 (hall A): compute, 17 kW, air cooling.
- Rack 28 (hall A): storage, 14 kW, air cooling. Contains the console server of the rack group.
- Racks 29 to 32 (hall S): storage, 12 kW, air cooling. Power feed b on a temporary circuit until the next facility window.

### 3.4. Racks of TMP1

- Racks 1 and 2 (hall A): infra, 8 kW, air cooling.
- Rack 3 (hall A): storage, 12 kW, air cooling.
- Rack 4 (hall A): storage, 10 kW, rear door cooling. Power feed b on a temporary circuit until the next facility window.
- Rack 5 (hall A): compute, 12 kW, air cooling.
- Rack 6 (hall A): infra, 14 kW, air cooling.
- Rack 7 (hall A): storage, 12 kW, air cooling. Reserved for tenant hardware.
- Rack 8 (hall A): compute, 12 kW, rear door cooling.
- Rack 9 (hall A): infra, 17 kW, air cooling.
- Rack 10 (hall A): GPU, 34 kW, liquid cooling.
- Rack 11 (hall A): compute, 14 kW, air cooling.
- Rack 12 (hall A): mixed, 12 kW, rear door cooling.
- Rack 13 (hall A): GPU, 34 kW, liquid cooling. The rear door heat exchanger is shared with the next rack.
- Rack 14 (hall A): GPU, 30 kW, liquid cooling.
- Rack 15 (hall A): GPU, 10 kW, air cooling.
- Rack 16 (hall A): GPU, 34 kW, liquid cooling.
- Racks 17 and 18 (hall A): compute, 10 kW, air cooling.
- Rack 19 (hall A): infra, 14 kW, air cooling. Half empty because of the power budget.
- Rack 20 (hall A): GPU, 30 kW, liquid cooling.
- Rack 21 (hall A): compute, 10 kW, air cooling. Planned for a refresh in 2027.
- Rack 22 (hall A): GPU, 34 kW, liquid cooling. Nodes from the 2021 purchase, out of vendor support in 2027.
- Rack 23 (hall A): compute, 10 kW, rear door cooling.
- Rack 24 (hall A): infra, 12 kW, air cooling.

### 3.5. Racks of ESP1

- Racks 1 and 2 (hall A): infra, 8 kW, air cooling.
- Racks 3 and 4 (hall A): storage, 14 kW, air cooling.
- Rack 5 (hall A): GPU, 10 kW, air cooling.
- Rack 6 (hall A): compute, 14 kW, air cooling.
- Rack 7 (hall A): compute, 17 kW, rear door cooling. Contains the console server of the rack group.
- Rack 8 (hall A): compute, 12 kW, rear door cooling.
- Rack 9 (hall A): GPU, 10 kW, rear door cooling. Nodes from the 2021 purchase, out of vendor support in 2027.
- Rack 10 (hall A): compute, 17 kW, air cooling.
- Rack 11 (hall A): compute, 14 kW, air cooling. Power feed b on a temporary circuit until the next facility window.
- Rack 12 (hall A): GPU, 12 kW, air cooling.
- Rack 13 (hall A): storage, 12 kW, air cooling.
- Rack 14 (hall A): mixed, 12 kW, rear door cooling.
- Rack 15 (hall A): compute, 12 kW, air cooling.
- Rack 16 (hall A): mixed, 17 kW, rear door cooling.
- Rack 17 (hall A): GPU, 14 kW, air cooling.
- Rack 18 (hall A): GPU, 12 kW, air cooling. Contains the console server of the rack group.
- Rack 19 (hall A): mixed, 12 kW, air cooling.
- Rack 20 (hall A): GPU, 12 kW, air cooling.
- Rack 21 (hall A): compute, 14 kW, air cooling.
- Rack 22 (hall A): infra, 12 kW, rear door cooling. Contains the console server of the rack group.
- Rack 23 (hall A): compute, 10 kW, air cooling. Power feed b on a temporary circuit until the next facility window.
- Racks 24 and 25 (hall A): storage, 10 kW, air cooling. Contains loaner nodes of a vendor.
- Rack 26 (hall A): GPU, 12 kW, air cooling. Contains loaner nodes of a vendor.
- Rack 27 (hall A): mixed, 12 kW, rear door cooling. Half empty because of the power budget.
- Rack 28 (hall A): storage, 17 kW, rear door cooling.
- Rack 29 (hall A): GPU, 14 kW, rear door cooling.
- Rack 30 (hall A): storage, 12 kW, air cooling.
- Rack 31 (hall A): infra, 12 kW, air cooling. Power feed b on a temporary circuit until the next facility window.
- Rack 32 (hall A): compute, 17 kW, rear door cooling.
- Rack 33 (hall A): GPU, 10 kW, air cooling.
- Rack 34 (hall A): mixed, 10 kW, air cooling. Planned for a refresh in 2027.
- Racks 35 and 36 (hall A): compute, 10 kW, air cooling. Planned for a refresh in 2027.

### 3.6. Rack notes

The rack notes give the state of each rack on the date of this revision: the installed nodes, the free slots, the switch models and the result of the last physical audit. The site teams update the notes in the inventory system; this section is a copy for planning. Only the racks with a finding in the last audit or a change since revision 13 are listed.

#### Rack notes of HEL1

Rack 1, hall A, infra. Nodes: 6 NL-I1 and 3 NL-M1. Free rack units: 29. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in February 2026: PDU B outlet 14 defective, ticket opened.

Rack 6, hall A, infra. Nodes: 1 NL-I1 and 1 NL-M1. Free rack units: 36. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in June 2026: no findings.

Rack 8, hall A, GPU. Nodes: 4 NL-G8 and 1 NL-G4L. Free rack units: 18. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in March 2026: two cable labels replaced.

Rack 14, hall A, mixed. Nodes: 8 NL-C4 and 5 NL-S24. Free rack units: 12. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in January 2026: no findings.

Rack 17, hall A, compute. Nodes: 4 NL-C2 and 8 NL-C4. Free rack units: 18. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in August 2026: door lock replaced.

Rack 24, hall A, GPU. Nodes: 3 NL-G8 and 1 NL-G4L. Free rack units: 22. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in May 2026: no findings.

Rack 28, hall A, infra. Nodes: 6 NL-I1 and 5 NL-M1. Free rack units: 27. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in February 2026: no findings.

Rack 37, hall A, storage. Nodes: 3 NL-S24 and 7 NL-S60. Free rack units: 4. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in June 2026: one cable not in the inventory system, record added.

Rack 42, hall A, compute. Nodes: 4 NL-C2 and 5 NL-C4. Free rack units: 24. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in February 2026: PDU B outlet 14 defective, ticket opened.

Rack 44, hall A, infra. Nodes: 2 NL-I1 and 6 NL-M1. Free rack units: 30. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in October 2026: no findings.

#### Rack notes of HEL2

Rack 2, hall A, infra. Nodes: 1 NL-I1 and 4 NL-M1. Free rack units: 33. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in April 2026: one cable not in the inventory system, record added.

Rack 3, hall A, compute. Nodes: 4 NL-C2 and 8 NL-C4. Free rack units: 18. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in September 2026: one blanking panel missing, installed during the audit.

Rack 10, hall A, infra. Nodes: 8 NL-I1 and 2 NL-M1. Free rack units: 28. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in August 2026: PDU B outlet 14 defective, ticket opened.

Rack 19, hall A, compute. Nodes: 3 NL-C2 and 1 NL-C4. Free rack units: 33. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in April 2026: one cable not in the inventory system, record added.

Rack 20, hall A, compute. Nodes: 8 NL-C2 and 5 NL-C4. Free rack units: 20. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in March 2026: one blanking panel missing, installed during the audit.

Rack 28, hall A, GPU. Nodes: 1 NL-G8 and 1 NL-G4L. Free rack units: 30. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in April 2026: one cable not in the inventory system, record added.

Rack 31, hall A, GPU. Nodes: 3 NL-G8 and 2 NL-G4L. Free rack units: 18. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in January 2026: no findings.

Rack 36, hall A, mixed. Nodes: 7 NL-C4 and 1 NL-S24. Free rack units: 22. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in October 2026: one cable not in the inventory system, record added.

Rack 43, hall B, compute. Nodes: 4 NL-C2 and 7 NL-C4. Free rack units: 20. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in March 2026: no findings.

Rack 45, hall B, mixed. Nodes: 8 NL-C4 and 8 NL-S24. Free rack units: 6. Leaf pair LEAF-64D, OOB switch OOB-48T-4X. Last audit in March 2026: no findings.

Rack 52, hall B, GPU. Nodes: 3 NL-G8 and 2 NL-G4L. Free rack units: 18. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in January 2026: no findings.

Rack 56, hall B, storage. Nodes: 5 NL-S24 and 2 NL-S60. Free rack units: 20. Leaf pair LEAF-64D, OOB switch OOB-48T-4X. Last audit in January 2026: PDU B outlet 14 defective, ticket opened.

Rack 63, hall B, mixed. Nodes: 2 NL-C4 and 3 NL-S24. Free rack units: 28. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in October 2026: one cable not in the inventory system, record added.

#### Rack notes of OUL1

Rack 3, hall A, mixed. Nodes: 4 NL-C4 and 2 NL-S24. Free rack units: 26. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in September 2026: no findings.

Rack 6, hall A, infra. Nodes: 2 NL-I1 and 1 NL-M1. Free rack units: 35. Leaf pair LEAF-64D, OOB switch OOB-48T-4X. Last audit in March 2026: no findings.

Rack 7, hall A, infra. Nodes: 8 NL-I1 and 7 NL-M1. Free rack units: 23. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in October 2026: no findings.

Rack 15, hall A, mixed. Nodes: 5 NL-C4 and 7 NL-S24. Free rack units: 14. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in February 2026: PDU B outlet 14 defective, ticket opened.

Rack 20, hall A, compute. Nodes: 4 NL-C2 and 6 NL-C4. Free rack units: 22. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in August 2026: no findings.

Rack 23, hall A, compute. Nodes: 5 NL-C2 and 3 NL-C4. Free rack units: 27. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in May 2026: no findings.

Rack 25, hall A, GPU. Nodes: 1 NL-G8 and 1 NL-G4L. Free rack units: 30. Leaf pair LEAF-64D, OOB switch OOB-48T-2Q. Last audit in March 2026: door lock replaced.

Rack 27, hall A, compute. Nodes: 3 NL-C2 and 8 NL-C4. Free rack units: 19. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in August 2026: door lock replaced.

#### Rack notes of TMP1

Rack 2, hall A, infra. Nodes: 3 NL-I1 and 4 NL-M1. Free rack units: 31. Leaf pair LEAF-64D, OOB switch OOB-48T-2Q. Last audit in March 2026: one cable not in the inventory system, record added.

Rack 6, hall A, infra. Nodes: 2 NL-I1 and 3 NL-M1. Free rack units: 33. Leaf pair LEAF-64D, OOB switch OOB-48T-4X. Last audit in August 2026: one cable not in the inventory system, record added.

Rack 7, hall A, storage. Nodes: 4 NL-S24 and 2 NL-S60. Free rack units: 22. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in October 2026: no findings.

Rack 9, hall A, infra. Nodes: 2 NL-I1 and 7 NL-M1. Free rack units: 29. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in September 2026: no findings.

Rack 12, hall A, mixed. Nodes: 5 NL-C4 and 2 NL-S24. Free rack units: 24. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in January 2026: no findings.

Rack 15, hall A, GPU. Nodes: 1 NL-G8 and 3 NL-G4L. Free rack units: 22. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in May 2026: no findings.

Rack 19, hall A, infra. Nodes: 5 NL-I1 and 3 NL-M1. Free rack units: 30. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in January 2026: dust filter of the rear door cleaned.

#### Rack notes of ESP1

Rack 5, hall A, GPU. Nodes: 2 NL-G8 and 2 NL-G4L. Free rack units: 22. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in September 2026: one blanking panel missing, installed during the audit.

Rack 9, hall A, GPU. Nodes: 3 NL-G8 and 2 NL-G4L. Free rack units: 18. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in August 2026: one cable not in the inventory system, record added.

Rack 16, hall A, mixed. Nodes: 5 NL-C4 and 7 NL-S24. Free rack units: 14. Leaf pair LEAF-32D, OOB switch OOB-48T-2Q. Last audit in September 2026: no findings.

Rack 20, hall A, GPU. Nodes: 4 NL-G8 and 3 NL-G4L. Free rack units: 10. Leaf pair LEAF-32D, OOB switch OOB-48T-4X. Last audit in October 2026: no findings.

## 4. Host names

**R-4.1** Each node has exactly one host name. The host name does not change while the node stays in the same rack position.

**R-4.2** The host name of a node is <site>-<role>-r<rack>-s<slot>, where <site> is the site code in lower case, <role> is the role code from table 4-1, <rack> is the rack number with two digits and <slot> is the slot with two digits. Example: hel1-gpu-r03-s07.

Table 4-1: Role codes

| Role | Code | Description |
|---|---|---|
| control-plane | cp | Kubernetes control plane and etcd |
| compute | cpu | CPU worker nodes |
| gpu | gpu | Accelerator worker nodes |
| storage | sto | Ceph OSD nodes and NFS gateways |
| infra | inf | Platform services: registry mirror, monitoring, bastion |

**R-4.3** Switches are named <site>-<function>-r<rack>, for example hel1-oob-r03 and hel1-leaf-r03a. Leaf switches get the suffix a or b.

**R-4.4** Spine switches are named <site>-spine-<number>, numbered from 1 in each site.

**R-4.5** PDUs are named <site>-pdu-r<rack><side>, for example oul1-pdu-r12a.

**R-4.6** Console servers are named <site>-con-r<rack>.

**R-4.7** The DNS name of a node is its host name in the zone <site>.nordlake.internal. Section 14 gives the zones.

**R-4.8** The BMC of a node has the DNS name <host name>-bmc in the same zone.

**R-4.9** Host names must not contain upper case letters, underscores or dots.

**R-4.10** A node that moves to a new rack position gets a new host name. The old name stays reserved for 90 days.

**R-4.11** Virtual machines are not named with this rule. Their names come from the tenant that owns them.

## 5. IPv4 address plan

**R-5.1** The platform uses the private range 10.0.0.0/8. Public addresses are only used on the site border and are outside the scope of this standard.

**R-5.2** The second octet of an address identifies the network type and the site: the site octet S (table 2-1) for the out-of-band network, S + 64 for the in-band management network and S + 96 for the data network. The storage network uses 172.16.0.0/12 (R-5.6).

**R-5.3** Addresses are never assigned by hand on nodes. The provisioning system (section 16) assigns them from the rules of this standard.

**R-5.4** Loopback and point-to-point addresses of switches come from 10.255.0.0/16. Section 10 gives the details.

**R-5.5** Each site keeps the range S.0.0.0 to S.0.255.255 in its out-of-band block (10.S.0.0/24 and 10.S.250.0/24 to 10.S.255.0/24) for site-wide services: the out-of-band jump host, the console aggregation and the PDU management server.

**R-5.6** The storage network of a site uses 172.(16 + n).0.0/16, where n is the index of the site in table 2-1, starting at 0. Each rack has one /24 in that range, with the rack number as the third octet.

**R-5.7** Tenant overlay networks use 100.64.0.0/10 and never appear on node interfaces outside of the overlay.

Table 5-1: Address ranges by network, for site octet S and rack R

| Network | Range for a rack | Gateway | Rule |
|---|---|---|---|
| Out-of-band | 10.S.R.0/24 | .1 | R-6.3 |
| In-band management | 10.(S+64).R.0/25 | .1 | R-7.2 |
| Data | 10.(S+96).R.0/24 | anycast .1 | R-9.6 |
| Storage | 172.(16+n).R.0/24 | none (L2 only) | R-17.2 |

The table gives the normal ranges. Section 19 lists the site deviations that change some of these ranges.

### 5.1. Design notes

The address plan puts the site and the network type into the second octet and the rack into the third octet. This makes it possible to see from an address where a device is, without a lookup in the inventory system. The site teams asked for this property after the first years of operation at HEL1, when addresses were assigned from a pool and nobody could find a device from an alert without the inventory system.

The cost of the plan is a large number of small subnets and a fixed limit of 255 racks for each site and network. No site is near this limit. The plan also wastes addresses, because most racks have fewer than 40 nodes. The private range is large enough, so this was accepted.

The rack infrastructure gets fixed low addresses in each rack subnet, and the nodes get addresses from the slot. A node keeps its address while it stays in the same position, also after a replacement of the mainboard. This is important for the BMCs, because the site teams use the BMC address of a slot when they replace a node and the new BMC is not yet in the inventory system.

The storage network uses a different private range (172.16.0.0/12) because it is not routed. Overlap with tenant networks is not possible, because tenants cannot reach the storage network directly.

## 6. Out-of-band management network

The out-of-band (OOB) network is a separate physical network. It must stay available when the data fabric, the in-band management network or a node operating system fails. It has a lower bandwidth than the other networks and carries only management traffic.

**R-6.1** Each rack has one OOB switch in U42 with 48 ports of 1 Gbit/s copper and two uplinks of 10 Gbit/s to the OOB aggregation switches of the hall.

**R-6.2** The OOB switch connects the BMC port of each node, the management ports of the leaf switches, the two PDUs and the console server, if the rack has one.

**R-6.3** Each rack has one OOB subnet, 10.S.R.0/24, where S is the site octet and R is the rack number.

**R-6.4** The BMC of a node gets the address 10.S.R.H in the OOB subnet of its rack, where H is the slot of the node plus 20. The host octets 2 to 20 of each OOB subnet are reserved for the rack infrastructure: the OOB switch (.2), the PDUs (.3 and .4), the console server (.5) and the leaf switch management ports (.6 and .7). The other reserved addresses are for future rack devices. Example: the BMC of the node in HEL1, rack 3, slot 7 has the address 10.16.3.27.

**R-6.5** The default gateway of an OOB subnet is the first address of the subnet, .1. It is an SVI on the OOB aggregation switches with VRRP. The prefix length on BMCs is /24.

**R-6.6** BMC addresses are static in the BMC configuration. DHCP on the OOB network is only used for the first start of a new BMC, from the range .200 to .239, and the provisioning system then sets the static address.

**R-6.7** The OOB network has no route to the internet. Firmware downloads go through the OOB jump host (R-5.5).

**R-6.8** Only the hosts in the management security zone (section 18) can reach the OOB network.

**R-6.9** The OOB aggregation switches of a hall are a pair with MLAG. Each rack OOB switch has one uplink to each.

**R-6.10** A BMC that is not reachable for more than 15 minutes creates a ticket for the site team (section 20).

### 6.1. Procedure: replace a rack OOB switch

1. Open a normal change record. The BMCs of the rack are not reachable during the work, so the change must not overlap with provisioning or firmware work in the same rack.
2. Export the running configuration of the old switch from the network automation pipeline. Do not copy the configuration from the switch itself.
3. Label the cables with the port numbers if the labels are not readable. The port of a BMC is the slot of the node (R-12.5).
4. Remove the old switch and install the new switch in U42. Connect the two uplinks first, then the PDUs and the console server, then the BMCs.
5. Start the new switch. It gets its first address from the OOB provisioning DHCP range of the aggregation switches, and the pipeline then applies the configuration of the rack.
6. Check that each BMC of the rack answers on its address. The monitoring dashboard "OOB rack view" shows the state of each address of the rack subnet.
7. Update the serial number in the inventory system.
8. Close the change record with the list of BMCs that did not answer, if any, and the ticket numbers for them.

### 6.2. Procedure: renumber a BMC after a node move

When a node moves to a new rack position, its BMC address changes, because the address follows the rack and the slot (R-6.4). The provisioning system makes the change; the site team must not set the address by hand. The provisioning system first sets the new static address through the old address, then the site team moves the node and connects the BMC port to the OOB switch port of the new slot. The old address stays reserved for 90 days, the same as the old host name (R-4.10), so that old monitoring data is not mixed with the data of a new node in the old position. If the node moves to another site, it is handled as a new node: the inventory record is closed and a new record is opened in the new site.

HEL1: the OOB aggregation pair of hall A is hel1-oobagg-1 and hel1-oobagg-2 in rack 2. The OOB jump host is hel1-oobjump-1 at 10.16.0.10. The console aggregation server is at 10.16.0.20.

HEL2: the OOB aggregation pair of hall A is hel2-oobagg-1 and hel2-oobagg-2 in rack 1. The OOB jump host is hel2-oobjump-1 at 10.17.0.10. The console aggregation server is at 10.17.0.20.

OUL1: the OOB aggregation pair of hall A is oul1-oobagg-1 and oul1-oobagg-2 in rack 2. The OOB jump host is oul1-oobjump-1 at 10.24.0.10.

TMP1: the OOB aggregation pair of hall A is tmp1-oobagg-1 and tmp1-oobagg-2 in rack 2. The OOB jump host is tmp1-oobjump-1 at 10.32.0.10. The console aggregation server is at 10.32.0.20.

ESP1: the OOB aggregation pair of hall A is esp1-oobagg-1 and esp1-oobagg-2 in rack 1. The OOB jump host is esp1-oobjump-1 at 10.40.0.10. The console aggregation server is at 10.40.0.20.

### 6.3. OOB aggregation design

The OOB aggregation pair of a hall terminates the uplinks of all rack OOB switches of the hall. It routes between the OOB subnets of the racks and the site-wide OOB block (R-5.5), and it is the only path from the management security zone to the OOB network. The pair has no route to the data fabric. A failure of the data fabric therefore does not affect the OOB network, which is the purpose of a separate network.

Each rack OOB switch has one uplink to each switch of the pair, and the two uplinks form one MLAG bundle. The OOB subnet of the rack is a VLAN on the bundle with the gateway as an SVI with VRRP on the pair (R-6.5). The aggregation switches have one port for each rack of the hall and a reserve of 25 % for new racks.

The aggregation pair connects to the firewall cluster of the site through two 10 Gbit/s links. The firewall rules for the OOB network are in section 18.

### 6.4. Rack infrastructure devices

The PDUs of a rack have one management card each. PDU A uses the address .3 and PDU B the address .4 of the OOB subnet of the rack. New PDU models with two management cards use the second card only for the redundant power monitoring, with the addresses .8 and .9. The console server, if the rack has one, uses .5. The management ports of the leaf switches use .6 (leaf a) and .7 (leaf b).

The addresses .10 to .20 are reserved for future rack devices, for example a rack door controller or a liquid cooling controller. The addresses above .20 are for the BMCs of the nodes (R-6.4), and the addresses .200 to .239 are the DHCP range for new BMCs (R-6.6). The last addresses of the subnet, .250 to .254, are reserved for test equipment that the site team connects during an installation.

A device that is not in this list must not get an address in an OOB subnet. A request for a new device type goes to Platform Network Engineering, which gives it an address from the reserved range and adds it to this section.

### 6.5. Site notes for the OOB network

HEL1: At HEL1, the OOB aggregation pair is in rack 6. The console aggregation server of HEL1 keeps the console logs for 30 days.

HEL2: The OOB network of HEL2 has 6 spare rack OOB switches in the local stock. The site team of HEL2 checks the OOB uplinks every quarter.

OUL1: The OOB aggregation switches of OUL1 were replaced in 2025. The console aggregation server of OUL1 keeps the console logs for 30 days.

TMP1: The OOB network of TMP1 has 3 spare rack OOB switches in the local stock. The console aggregation server of TMP1 keeps the console logs for 30 days.

ESP1: At ESP1, the OOB aggregation pair is in rack 18. The site team of ESP1 checks the OOB uplinks every quarter.

## 7. In-band management network

**R-7.1** Each node has one in-band management interface. It is the first 25 Gbit/s port of the node (port 1 of the network card in PCIe slot 1).

**R-7.2** The in-band management subnet of rack R is 10.(S+64).R.0/25. The node gets the host octet slot + 10. The upper half of the /24 (.128 to .255) is reserved for virtual IPs of platform services in that rack.

**R-7.3** The in-band management interface is an access port in the management VLAN of the rack. The node does not tag the traffic.

**R-7.4** SSH to nodes is only allowed from the bastion hosts and from the configuration management servers.

**R-7.5** The in-band management network carries the Kubernetes API traffic of the control plane nodes, the configuration management traffic, the log shipping and the metrics scraping.

**R-7.6** The in-band management gateway is .1 of the subnet, an anycast gateway on both leaf switches of the rack.

**R-7.7** Nodes must not route between the in-band management network and the data network.

**R-7.8** The management VLAN of a rack has the ID 100 + R for racks 1 to 99.

At HEL1, the bastion hosts are hel1-inf-bastion-1, hel1-inf-bastion-2. The configuration management servers are in rack 4 and rack 5. Log shipping uses a dedicated Vector aggregator pair in the same racks.

At HEL2, the bastion hosts are hel2-inf-bastion-1, hel2-inf-bastion-2, hel2-inf-bastion-3. The configuration management servers are in rack 1 and rack 9. The site has a local log buffer of 7 days in case the link to the central log cluster fails.

At OUL1, the bastion hosts are oul1-inf-bastion-1, oul1-inf-bastion-2, oul1-inf-bastion-3, oul1-inf-bastion-4. The configuration management servers are in rack 3 and rack 8. Log shipping uses a dedicated Vector aggregator pair in the same racks.

At TMP1, the bastion hosts are tmp1-inf-bastion-1, tmp1-inf-bastion-2. The configuration management servers are in rack 3 and rack 5. The site has a local log buffer of 7 days in case the link to the central log cluster fails.

At ESP1, the bastion hosts are esp1-inf-bastion-1, esp1-inf-bastion-2, esp1-inf-bastion-3, esp1-inf-bastion-4. The configuration management servers are in rack 4 and rack 5. Log shipping goes to the central log cluster in HEL1 over the in-band management network.

### 7.1. Notes on the in-band management network

The in-band management network has its own port on each node, so that a configuration error on the data bond does not stop the access of the configuration management system. A node with a wrong data bond configuration is still reachable through SSH from the bastion hosts and can be corrected without the BMC console.

The in-band management network does not carry storage traffic or tenant traffic. Large file transfers, for example operating system images, use the provisioning VLAN during the installation and the data network after the installation.

### 7.2. Migration from the old management switches

Until 2023, some racks had a separate management switch for the in-band management ports. These racks are being moved to the management patch panel and the leaf switches (R-12.6). The migration changes the cabling but not the addresses of the nodes: the in-band management subnet and the host octets stay the same. During the migration of a rack, the nodes keep their access through the data network, and the site team uses the BMC console only if a node does not come back.

### 7.3. Virtual IP addresses

Platform services that need a fixed address in a rack, for example the API endpoint of a control plane or the address of an ingress controller for the management zone, use the upper half of the in-band management subnet of the rack (R-7.2). The platform API assigns these addresses; the address stays with the service while the service runs in the same rack. Keepalived or the cluster load balancer moves the address between the nodes of the rack. A virtual IP address cannot move to another rack, because the subnet is local to the rack.

### 7.4. Site notes for the in-band management network

HEL1: At HEL1, the bastion hosts have a second interface in the OOB network for emergencies. All in-band management ports at HEL1 are 25 Gbit/s. SSH access from outside the site goes through the bastion hosts of HEL1 only.

HEL2: At HEL2, the bastion hosts have a second interface in the OOB network for emergencies. The management ports of the oldest nodes at HEL2 are 10 Gbit/s; they are replaced during the refresh in 2025. The site team of HEL2 uses the in-band management network for the hardware inventory scans every night.

OUL1: The configuration management servers of OUL1 use the in-band management network of rack 20. 9 racks at OUL1 still use a separate management switch instead of the management patch panel; the migration is planned for 2026. SSH access from outside the site goes through the bastion hosts of OUL1 only.

TMP1: The in-band management network of TMP1 has a separate uplink to the log cluster. The management ports of the oldest nodes at TMP1 are 10 Gbit/s; they are replaced during the refresh in 2024. SSH access from outside the site goes through the bastion hosts of TMP1 only.

ESP1: The configuration management servers of ESP1 use the in-band management network of rack 4. 5 racks at ESP1 still use a separate management switch instead of the management patch panel; the migration is planned for 2024. SSH access from outside the site goes through the bastion hosts of ESP1 only.

## 8. BMC configuration

This section gives the configuration of the BMC of a node, after the BMC has its address (R-6.4). The provisioning system applies the configuration through Redfish.

**R-8.1** The BMC must use the firmware version that the platform firmware baseline gives for the node model. The baseline is updated each quarter.

**R-8.2** Only Redfish over HTTPS and SSH to the BMC are enabled. IPMI over LAN must be disabled.

**R-8.3** The BMC certificate comes from the internal OOB certificate authority. Self-signed certificates are replaced during provisioning.

**R-8.4** Local BMC accounts: one break-glass account, with a password in the vault, and one service account for the provisioning system. All other access is through LDAP to the OOB directory.

**R-8.5** The BMC password of the break-glass account is rotated every 90 days and after each use.

**R-8.6** Serial-over-LAN is enabled at 115200 baud. The console log of the node goes to the console aggregation server.

**R-8.7** The BMC sends its event log to the syslog server of the site at 10.S.0.30 over TLS.

**R-8.8** SNMP on the BMC is disabled. Monitoring reads the sensors through Redfish (section 20).

**R-8.9** The BMC time comes from the NTP servers of the site in the OOB network (section 15).

**R-8.10** Virtual media is enabled only during provisioning and during a reinstallation. The provisioning system disables it after use.

**R-8.11** The power restore policy of a node is "last state", except for control plane nodes, which use "always on".

**R-8.12** The BMC host name is the host name of the node with the suffix -bmc.

**R-8.13** The BMC network interface is the dedicated BMC port. The shared LOM port must be disabled.

**R-8.14** The BMC VLAN setting must be off, because the OOB switch port is an access port.

Table 8-1: BMC firmware baseline, quarter 4 of 2026

| Node model | BMC vendor | Baseline firmware | Minimum firmware | Notes |
|---|---|---|---|---|
| NL-C2 | Vendor A | 3.61.1 | 3.9.2 | Update the CPLD first |
| NL-C4 | Vendor B | 5.25.5 | 5.6.4 | Two-step update |
| NL-G8 | Vendor A | 1.25.4 | 1.5.8 |  |
| NL-G4L | Vendor A | 1.77.4 | 1.6.0 | Resets the BMC network settings: run the provisioning step again |
| NL-S24 | Vendor A | 2.64.7 | 2.7.0 | Resets the BMC network settings: run the provisioning step again |
| NL-S60 | Vendor A | 4.73.3 | 4.8.1 |  |
| NL-M1 | Vendor B | 1.39.5 | 1.6.2 | Resets the BMC network settings: run the provisioning step again |
| NL-I1 | Vendor B | 5.50.3 | 5.3.7 | Needs a host reboot |

Known problems with BMC firmware are tracked in the platform firmware register. The site teams must not install a firmware version that is not in the baseline, also when the vendor recommends it.

### 8.1. Known BMC problems

The list gives the known problems of the BMCs in the fleet that affect the network or the provisioning. Problems that are corrected in the current baseline are kept for one year, because nodes in the quarantine pool can still have old firmware.

BMC-101. Model NL-S60: the BMC loses its static address after a cold start and asks for a DHCP address. Action: set the address again through the provisioning system; the baseline firmware corrects it. Status: open, vendor case opened.

BMC-102. Model NL-S60: the Redfish service stops answering after about 40 days of uptime. Action: restart the BMC through the OOB switch port (shut and no shut) or through the PDU outlet of the node. Status: corrected in the baseline.

BMC-103. Model NL-S60: the BMC answers ARP requests for the address of the host operating system. Action: disable the shared LOM port (R-8.13); the problem occurs only when it is enabled. Status: corrected in the baseline, keep for one year.

BMC-104. Model NL-G4L: virtual media mounts fail when the image is larger than 4 GiB. Action: use the HTTP boot path of the provisioning system instead of virtual media. Status: corrected in the baseline, keep for one year.

BMC-105. Model NL-I1: the sensor readings of the GPU board are missing in Redfish. Action: update the GPU board CPLD first, then the BMC firmware. Status: corrected in the baseline, keep for one year.

BMC-106. Model NL-G4L: the BMC sends syslog without TLS after a factory reset. Action: run the provisioning step "BMC configuration" again. Status: open, vendor case opened.

BMC-107. Model NL-C4: SSH to the BMC rejects keys of type ed25519. Action: use RSA keys of 4096 bits for the BMC service account until the next baseline. Status: corrected in the baseline, keep for one year.

BMC-108. Model NL-G4L: the BMC web server uses the self-signed certificate after a firmware update. Action: the provisioning system installs the OOB certificate again in its daily check. Status: open, no fix planned by the vendor.

BMC-109. Model NL-G4L: the power restore policy changes to "always off" after a firmware update. Action: the daily compliance check corrects it; check control plane nodes by hand after each update. Status: open, vendor case opened.

BMC-110. Model NL-G4L: the BMC does not accept the VLAN setting "off" and keeps VLAN 1. Action: configure the OOB switch port as an access port in VLAN 1 for this model until the fix is available. Status: corrected in the baseline.

BMC-111. Model NL-C2: the BMC time drifts by several minutes per day. Action: the NTP client of the BMC is disabled after a reset; run the provisioning step again. Status: open, vendor case opened.

BMC-112. Model NL-G8: the BMC event log fills up and stops recording. Action: clear the event log through Redfish; the hardware exporter does this when the log is 90 % full. Status: open, vendor case opened.

BMC-113. Model NL-S60: LDAP login to the BMC fails when the group name contains a space. Action: use the group names without spaces from the OOB directory. Status: open, vendor case opened.

BMC-114. Model NL-C4: the BMC reports a fan failure for a fan slot that the chassis does not have. Action: ignore the alert for this model; the monitoring rule has an exception. Status: open, vendor case opened.

### 8.2. Security notes for BMCs

A BMC has full control of its node: it can change the BIOS settings, mount virtual media and read the console. Access to a BMC is therefore treated the same as root access to the node. The rules of section 8 and of section 18 limit the access to the bastion hosts, the provisioning system and the hardware exporter.

The break-glass account is for the case that the OOB directory is not available. Each use creates an alert for the security team, and the password is rotated after the use (R-8.5). The site teams must document the reason in the incident record.

Vendor support engineers do not get BMC accounts. When the vendor needs BMC data, the site team exports the data (for example the event log or a support bundle) and sends it through the vendor case.

### 8.3. Firmware update process

The firmware tooling updates the BMC firmware of running nodes in the maintenance window of the site. An update of the BMC firmware does not stop the node, but the BMC is not reachable for several minutes. The tooling updates at most 10 % of the BMCs of a rack at the same time, so that the rack view in the monitoring keeps most of its sensor data.

BIOS and network card updates need a restart of the node. The tooling asks the cluster to drain the node, updates the firmware, restarts the node and checks the result. A node that does not come back after the update stays drained, and the tooling opens a ticket for the site team.

The firmware tooling records the firmware versions of each node in the inventory system after each update. The compliance report compares the versions with the baseline every day.

### 8.4. Redfish usage

The provisioning system, the hardware exporter and the firmware tooling use Redfish. Each tool has its own service account in the OOB directory with the smallest set of privileges that it needs: the hardware exporter can only read, the firmware tooling can update firmware and restart the BMC, and the provisioning system can change the configuration. The tools must not use the break-glass account.

Redfish sessions are closed after use. Some BMC models allow only a small number of sessions, and a tool that leaves sessions open can block the access of the other tools. The hardware exporter uses basic authentication for each request instead of sessions for this reason.

### 8.5. Site notes for BMCs

HEL1: The BMCs of the GPU nodes at HEL1 need a manual step for each firmware update, because of a vendor tool. The hardware exporter of HEL1 reads about 700 BMCs in each 5-minute cycle. BMC logins at HEL1 use the OOB directory in HEL1 when the local replica is not available.

HEL2: HEL2 has 9 nodes in the quarantine pool with BMC firmware below the minimum version. The hardware exporter of HEL2 runs on the infra nodes in rack 24. The site team of HEL2 tests the break-glass account of one random BMC every month.

OUL1: All BMCs at OUL1 were on the baseline at the last compliance check. The hardware exporter of OUL1 reads about 700 BMCs in each 5-minute cycle. The OOB directory replica for OUL1 is on the OOB jump host.

TMP1: The BMCs of the GPU nodes at TMP1 need a manual step for each firmware update, because of a vendor tool. The hardware exporter of TMP1 reads about 500 BMCs in each 5-minute cycle. BMC logins at TMP1 use the OOB directory in HEL1 when the local replica is not available.

ESP1: The BMCs of the GPU nodes at ESP1 need a manual step for each firmware update, because of a vendor tool. At ESP1, the BMC event logs are also copied to the central log cluster. The site team of ESP1 tests the break-glass account of one random BMC every month.

## 9. Switch fabric

**R-9.1** The data network and the storage network of a site share one leaf-spine fabric with EVPN-VXLAN.

**R-9.2** Each rack has two leaf switches, a and b, in U40 and U41. Each node connects one port to each leaf.

**R-9.3** Each leaf has one 400 Gbit/s uplink to each spine of the site. A site has 4 spines, or 8 at HEL2.

**R-9.4** Leaf switches run as an EVPN multihoming pair with ESI. MLAG is not used in the data fabric.

**R-9.5** The spine switches do not connect to nodes. They only connect leaf switches and the border leaf pair.

**R-9.6** The data network gateway of a rack is an anycast gateway on both leaf switches, address .1 of the data subnet of the rack.

**R-9.7** The fabric must stay usable when one spine fails or when one leaf of each rack fails at the same time.

**R-9.8** All switches of the fabric run the same network operating system version, except during an upgrade window.

**R-9.9** The border leaf pair of a site connects the fabric to the site routers and to the firewall cluster.

**R-9.10** Changes to the fabric configuration are made only through the network automation pipeline.

HEL1 has 4 spines (hel1-spine-1 to hel1-spine-4) and the border leaf pair hel1-bleaf-1 and hel1-bleaf-2 in rack 2. The spines are in the network room of the hall.

HEL2 has 8 spines (hel2-spine-1 to hel2-spine-8) and the border leaf pair hel2-bleaf-1 and hel2-bleaf-2 in rack 3. The spines are in the network room of the hall.

OUL1 has 4 spines (oul1-spine-1 to oul1-spine-4) and the border leaf pair oul1-bleaf-1 and oul1-bleaf-2 in rack 1. The spines are in two racks at the opposite ends of the hall, so that one rack failure does not stop more than half of the spines.

TMP1 has 4 spines (tmp1-spine-1 to tmp1-spine-4) and the border leaf pair tmp1-bleaf-1 and tmp1-bleaf-2 in rack 2. The spines are in the middle racks of the hall to keep the cable lengths short.

ESP1 has 4 spines (esp1-spine-1 to esp1-spine-4) and the border leaf pair esp1-bleaf-1 and esp1-bleaf-2 in rack 1. The spines are in the network room of the hall.

### 9.1. Procedure: upgrade the fabric

Fabric upgrades are normal changes. The network automation pipeline makes the upgrade in this order, and stops at the first failed check:

1. Check that all BGP sessions and all EVPN routes are in the expected state. The pipeline compares them with the state of the last successful run.
2. Upgrade the spines one at a time. Before each spine, the pipeline moves traffic away from it with a BGP route map and waits until the traffic on the spine is below 1 % of its normal value.
3. Upgrade leaf a of each rack, in groups of at most 8 racks. The nodes continue on leaf b.
4. Check the state of the bonds of all nodes in the group. A node with only one active member in its bond before the upgrade stops the upgrade of its rack.
5. Upgrade leaf b of each rack, in the same groups.
6. Upgrade the border leaf pair, one switch at a time, in a separate window.
7. Compare the state with the state before the upgrade and close the change record.

### 9.2. Failure scenarios

The fabric is designed for the failure of one spine, of one leaf in each rack, or of one link of each node. In these cases the capacity is lower, but all nodes stay connected. The failure of both leaf switches of a rack disconnects the data and storage networks of that rack; the nodes are still reachable through the in-band management network only if the management port goes through a different switch, which is not the case in the current design (R-12.6). The site teams therefore use the BMC console in this case.

A failure of the border leaf pair disconnects the site from the other sites and from the internet. The nodes inside the site can still talk to each other and to the storage systems. The platform services that need the central services (for example the central log cluster) buffer their data for at least 7 days.

### 9.3. Fabric telemetry

The switches stream interface counters, optical levels, BGP state and EVPN state with gNMI to the telemetry collectors of the site every 10 seconds. The collectors write the data to the monitoring system. A switch that stops streaming creates an alert after 2 minutes. The network automation pipeline uses the same data to check the state before and after a change (section 9.1).

### 9.4. Border and site routers

The border leaf pair connects the fabric to two site routers. The site routers terminate the links to the other sites and the internet transits. They are outside the fabric and are managed by the WAN team. The border leaf pair announces the aggregate routes of the site to the site routers and receives the default route and the routes of the other sites.

The firewall cluster of the site is between the border leaf pair and the site routers for traffic to the internet, and between the VRFs of the security zones for traffic inside the site (section 18).

### 9.5. Known fabric problems

The list gives the known problems of the switch software in the fabric that the site teams must know. The network team tracks them with the vendor.

NET-201. Problem: after a restart, a leaf switch can announce the EVPN routes of its hosts before the host ports are up, which drops traffic for up to 30 s. Workaround: the automation pipeline delays the BGP sessions after a restart by 60 s.

NET-202. Problem: an optical module of one vendor reports a receive level of -40 dBm for a few seconds after insertion. Workaround: the monitoring ignores the first 5 minutes after an insertion.

NET-203. Problem: ESI multihoming can stay in the wrong state when both leaf switches of a rack restart at the same time. Workaround: never restart both leaf switches of a rack in the same step; the pipeline enforces this.

NET-204. Problem: the BFD sessions flap when the CPU of a spine is above 90 % during a large route change. Workaround: the BFD interval on the spines is 300 ms, not lower; the vendor fix is planned.

NET-205. Problem: ARP suppression keeps a stale entry when a virtual IP address moves between nodes faster than once in 2 s. Workaround: keepalived on the platform nodes uses a minimum delay of 5 s before it moves an address.

NET-206. Problem: the LLDP data of some network cards contains the port name of the operating system and not the physical port. Workaround: the provisioning check uses the MAC address and not the port name.

NET-207. Problem: a large number of MAC moves can trigger the MAC move protection and block a host port. Workaround: the limit is set to 20 moves in 180 s on the node ports.

NET-208. Problem: the switch telemetry stops for one switch after a collector restart. Workaround: the collectors are restarted one at a time; the alert of R-20.2 finds the remaining cases.

NET-209. Problem: storm control counts LACP frames on some leaf models. Workaround: storm control is set only for broadcast and unknown unicast traffic.

NET-210. Problem: PFC watchdog can disable the storage priority on a port after a short pause storm. Workaround: the watchdog recovery time is 1 s; the monitoring reports each event.

### 9.6. Site notes for the fabric

HEL1: The spines of HEL1 are on network operating system 4.32.2F. HEL1 has 9 spare leaf switches in the local stock. The border leaf pair of HEL1 has two 400 Gbit/s links to each site router.

HEL2: The fabric of HEL2 was last upgraded in 2024. HEL2 has 8 spare leaf switches in the local stock. The border leaf pair of HEL2 has two 400 Gbit/s links to each site router.

OUL1: The fabric of OUL1 was last upgraded in 2026. The spare parts stock of OUL1 has one spine and 6 leaf switches. At OUL1, the site routers are in rack 29.

TMP1: The leaf switches of TMP1 are of two models; the older model is replaced during the refresh in 2026. TMP1 has 2 spare leaf switches in the local stock. The firewall cluster of TMP1 is a pair in active and standby mode.

ESP1: The leaf switches of ESP1 are of two models; the older model is replaced during the refresh in 2025. ESP1 has 7 spare leaf switches in the local stock. The firewall cluster of ESP1 is a pair in active and standby mode.

## 10. Routing

**R-10.1** The fabric uses eBGP between leaf and spine for the underlay. Each leaf pair has its own private ASN.

**R-10.2** The ASN of the leaf pair of rack R in site S is 4210000000 + 1000 * S + R. The spines of a site share the ASN 4210000000 + 1000 * S.

**R-10.3** The underlay uses the loopback addresses 10.255.S.R/32 for leaf a and 10.255.S.(R+128)/32 for leaf b.

**R-10.4** BGP sessions use BFD with an interval of 300 ms and a multiplier of 3.

**R-10.5** The EVPN overlay uses the same eBGP sessions as the underlay.

**R-10.6** Each tenant VRF has its own L3 VNI. The VNI numbers come from the tenant onboarding process.

**R-10.7** The default route comes from the border leaf pair. Nodes do not run BGP, except the load balancer nodes of the platform, which announce service addresses with BGP to the leaf switches of their rack.

**R-10.8** Route maps on the leaf switches accept from nodes only the prefixes of the service address pool of the site.

**R-10.9** Maximum-prefix limits: 200 prefixes on a node session, 12000 on a leaf-spine session.

Appendix C lists the leaf pairs of each site with their ASN, so that the site teams do not need to compute it.

### 10.1. Service address pools

The load balancer nodes of the platform announce service addresses from the pool of their site. Table 10-1 gives the pools. A tenant service gets its address from the pool through the platform API; nobody assigns a service address by hand.

Table 10-1: Service address pools

| Site | Pool | Size | Used for |
|---|---|---|---|
| HEL1 | 10.112.240.0/21 | 2048 | Tenant load balancers |
| HEL1 | 10.112.248.0/24 | 256 | Platform services |
| HEL2 | 10.113.240.0/21 | 2048 | Tenant load balancers |
| HEL2 | 10.113.248.0/24 | 256 | Platform services |
| OUL1 | 10.120.240.0/21 | 2048 | Tenant load balancers |
| OUL1 | 10.120.248.0/24 | 256 | Platform services |
| TMP1 | 10.128.240.0/21 | 2048 | Tenant load balancers |
| TMP1 | 10.128.248.0/24 | 256 | Platform services |
| ESP1 | 10.136.240.0/21 | 2048 | Tenant load balancers |
| ESP1 | 10.136.248.0/24 | 256 | Platform services |

HEL1: the load balancer nodes are in racks 28, 32. They announce the service addresses to both leaf switches of their rack. The BGP sessions to the leaf switches use passwords from the vault.

HEL2: the load balancer nodes are in racks 34, 56. The site uses three load balancer nodes because one rack has only one power feed. The BGP sessions use the TTL security check with a hop count of 1.

OUL1: the load balancer nodes are in racks 6, 13. They announce the service addresses to both leaf switches of their rack. The BGP sessions use the TTL security check with a hop count of 1.

TMP1: the load balancer nodes are in racks 12, 19. They announce the service addresses to both leaf switches of their rack. The BGP sessions to the leaf switches use passwords from the vault.

ESP1: the load balancer nodes are in racks 28, 30. The site uses three load balancer nodes because one rack has only one power feed. The BGP sessions to the leaf switches use passwords from the vault.

### 10.2. BGP session parameters

All BGP sessions in the fabric use the same timers: keepalive 3 s, hold time 9 s, and BFD as in R-10.4. Graceful restart is enabled on the spines and the leaf switches and disabled on the sessions to the load balancer nodes, because a load balancer node that restarts must withdraw its service addresses at once.

Sessions use the addresses of the point-to-point links between leaf and spine, from 10.255.(S + 128).0/24. The automation pipeline computes the link addresses from the rack number and the spine number; they are not listed in this standard.

### 10.3. Notes on the routing policy

The leaf switches accept routes from the load balancer nodes only for addresses of the service pools of their site (R-10.8). This stops a wrong configuration of a load balancer node from attracting the traffic of other networks. The prefix limits (R-10.9) give a second protection: a session that sends too many prefixes is closed, and the site team gets an alert.

The private ASNs follow a formula, so that the site teams and the automation can compute them. A leaf pair that is replaced keeps the ASN of its rack. The ASNs of the spines are the same for all spines of a site, which keeps the routes simple and avoids path hunting between the spines.

## 11. Interface settings

This section gives the settings of the node network interfaces. The provisioning system writes them to the network configuration of the node operating system.

**R-11.1** Node interfaces use auto-negotiation for speed and duplex, except for the 400 Gbit/s ports, which are set to 400G with RS-FEC on both sides.

**R-11.2** The MTU of the node interfaces is 9000 bytes on the data network and on the storage network, and 1500 bytes on the in-band management network and on the BMC. Switch ports of the fabric use an MTU of 9216 bytes to carry the VXLAN header.

**R-11.3** Nodes must not use an MTU larger than the value in R-11.2, also when the network card supports it.

**R-11.4** The data interfaces and the storage interfaces of a node are two bonds over the same two physical ports: bond0 (data) and bond1 (storage) are VLAN subinterfaces on one LACP bond of the two ports.

**R-11.5** The bond uses LACP with the fast rate and the layer3+4 hash policy.

**R-11.6** IPv6 is disabled on all node interfaces until the IPv6 plan (draft NCP-NET-STD-009) is approved.

**R-11.7** Receive and transmit ring sizes are set to the maximum value of the network card.

**R-11.8** Interrupt coalescing uses the adaptive mode of the driver. Fixed values need a performance test report.

**R-11.9** Offloads: TSO, GSO and GRO are on. LRO is off.

**R-11.10** The in-band management interface does not use a bond. It is a single port (R-7.1).

Table 11-1: Network cards and driver settings

| Card | Ports | Driver | Firmware baseline | Ring size |
|---|---|---|---|---|
| NIC-25-2P | 2P | mlx5_core | 25.34.1988 | 8192 |
| NIC-100-2P | 2P | ice | 19.19.2402 | 4096 |
| NIC-200-2P | 2P | ice | 29.4.2303 | 4096 |
| NIC-400-1P | 1P | bnxt_en | 18.5.1858 | 4096 |
| NIC-400-2P | 2P | mlx5_core | 30.7.3759 | 8192 |

### 11.1. Notes on the interface settings

Large frames reduce the CPU load of the nodes and increase the throughput of storage and of distributed training. They only work when all devices in the path accept them. A node with a larger setting than its path silently loses large packets, while small packets, for example ping and SSH, still work. This type of fault is hard to find, and it is the reason for the network check in the provisioning (section 16) that sends packets of the full size without fragmentation.

The bonds use LACP so that a cabling error, for example both ports connected to the same leaf, is found by the switch and shown in the monitoring. Static bonds do not show this type of error.

### 11.2. Bond failover test

The burn-in test (section 16) includes a failover test of the bond: the provisioning system disables the leaf port of one member, checks that traffic continues on the other member, enables the port again and repeats the test for the other member. The test also checks that LACP shows both members as active after the test. A node that fails the test stays in the quarantine pool.

### 11.3. Network card firmware

The network card firmware is part of the firmware baseline (R-8.1). A firmware update of a network card restarts the card, so the node must be drained first. The provisioning system updates the firmware in the firmware step; on running nodes the firmware tooling does it in the maintenance windows of the site.

Driver settings that are not in this section use the default of the driver in the operating system image of the platform. A change of a driver setting needs a performance test report and a change of this section.

## 12. Cabling and link aggregation

**R-12.1** Copper cables are used only inside a rack. Links between racks use optical fibre.

**R-12.2** DAC cables up to 3 m are allowed between a node and the leaf switches of its rack.

**R-12.3** Each cable has a label at both ends with the far-end device and port, for example "hel1-leaf-r03a e1/17".

**R-12.4** Node port 1 of the data card connects to leaf a, node port 2 to leaf b. The leaf port number is the slot of the node.

**R-12.5** The BMC port connects to the OOB switch port with the number of the slot of the node.

**R-12.6** The in-band management port connects to the leaf a port 33 + (slot mod 8) through the management patch panel.

**R-12.7** Spare fibre pairs: each rack has 4 spare pairs to each spine row.

**R-12.8** Cable colours: blue for data and storage, yellow for OOB, red for the in-band management network, green for console.

**R-12.9** Fibre cleaning and inspection are required before each new connection of a fibre.

**R-12.10** Cable records are kept in the inventory system. A cable change without a record is a process failure (section 21).

HEL1: the overhead trays are on two levels, upper for fibre and lower for copper. The longest leaf-spine link is 48 m.

HEL2: the overhead trays are on two levels, upper for fibre and lower for copper. The average length of a leaf-spine link is 41 m.

OUL1: the overhead trays are on two levels, upper for fibre and lower for copper. The longest leaf-spine link is 40 m.

TMP1: the overhead trays are on two levels, upper for fibre and lower for copper. The longest leaf-spine link is 87 m.

ESP1: the cable trays are on one level with separators. The longest leaf-spine link is 77 m.

### 12.1. Power cabling

Each node connects one power supply to PDU A and one to PDU B. The outlet number on each PDU is the slot of the node, for nodes of 1U and 2U. Nodes of 4U use the outlet of their slot and the next outlet for their second pair of power supplies, where the model has four supplies. Switches use the outlets 40 to 42.

The power cables have the same labels as the network cables (R-12.3). Power cables of GPU nodes with four supplies are of the C19 type; all others are C13.

The site team checks the phase balance of each PDU after a new node is connected. The difference between the phases must be less than 20 % of the load of the most loaded phase.

### 12.2. Procedure: recable a node

Recabling of a node is a standard change when the node stays in the same slot. The site team drains the node in the cluster, disconnects one data port at a time, and checks that the bond shows the other port as active before it disconnects the next. The BMC port and the in-band management port are moved last. After the work, the site team checks the bond state, the LLDP neighbours of each port and the cable labels, and records the new cables in the inventory system.

### 12.3. Transceivers

Only transceivers from the approved list of the network team are used. Transceivers from other sources can work, but the switch vendor does not support them and the optical monitoring values can be wrong. Short links inside a row use multimode optics; links between rows and to the spines use single-mode optics. Each site keeps a stock of spare transceivers of at least 5 % of the installed number of each type.

### 12.4. Site notes for cabling

HEL1: The cable records of HEL1 were last checked against the racks in 2024. HEL1 uses LC connectors for all single fibre pairs.

HEL2: At HEL2, 7 racks still have copper management cables without the colour code. HEL2 uses LC connectors for all single fibre pairs.

OUL1: At OUL1, 8 racks still have copper management cables without the colour code. Trunk cables at OUL1 are pre-terminated with MPO connectors.

TMP1: At TMP1, 3 racks still have copper management cables without the colour code. Trunk cables at TMP1 are pre-terminated with MPO connectors.

ESP1: The site team of ESP1 uses a label printer with the inventory system template. ESP1 uses LC connectors for all single fibre pairs.

## 13. VLAN plan

This section gives the VLAN IDs on the leaf switch ports toward the nodes. The VXLAN VNI of a VLAN is the VLAN ID plus 10000 * the site index (table 2-1 order, starting at 1).

**R-13.1** VLAN IDs 1 to 99 are reserved for the switch infrastructure. VLAN 1 is not used.

**R-13.2** The data VLAN of rack R is 1000 + R. All nodes of a rack are in the same data VLAN.

**R-13.3** The storage VLAN of rack R is 2000 + R. The storage VLAN does not have a gateway on the leaf switches: the storage network is a layer 2 network inside the site, stretched over the fabric with EVPN.

**R-13.4** The provisioning VLAN of a site is VLAN 10. It is the native VLAN on the data bond during the first start of a node and is removed after the installation.

**R-13.5** The management VLAN of rack R is 100 + R (R-7.8).

**R-13.6** VLAN IDs 3000 to 3999 are reserved for the transit VLANs of the tenant overlays. Nodes never use them.

**R-13.7** VLAN IDs 4000 to 4094 are reserved for the switch vendor and for future use.

**R-13.8** A VLAN ID that this section does not give must not be configured on a node port.

Table 13-1: VLANs on a node port, for rack R

| VLAN | ID | Tagged on the node | Rule |
|---|---|---|---|
| Provisioning | 10 | no (native, only during installation) | R-13.4 |
| Management | 100 + R | no (separate port) | R-13.5 |
| Data | 1000 + R | yes, bond0 | R-13.2 |
| Storage | 2000 + R | yes, bond1 | R-13.3 |

### 13.1. Notes on the VLAN plan

The VLAN IDs on the node ports are local to a rack: the same rack number in two sites gives the same VLAN ID, but the VNI is different, because it contains the site index. This keeps the configuration of the leaf switches of all sites the same, and only the VNI mapping is different.

The tenant overlays use their own VNIs and do not appear as VLANs on the node ports. The transit VLANs of the overlays (R-13.6) are only on the border leaf pair.

### 13.2. Changes of the VLAN plan

A change of the VLAN plan changes the configuration of all leaf switches and of all nodes of a site. It is therefore made only with a new revision of this standard and a migration plan. During the migration, the leaf switches carry the old and the new VLAN on the node ports, the nodes are moved to the new VLAN one rack at a time, and the old VLAN is removed after all nodes of the site use the new one. Tools that compute the VLAN of a node must use the current revision; the migration plan gives the dates.

## 14. DNS

**R-14.1** Each site has the zone <site>.nordlake.internal, for example hel1.nordlake.internal.

**R-14.2** The site DNS servers are two resolvers in the infra racks of the site. They forward the other internal zones to the central DNS servers in HEL1 and HEL2.

**R-14.3** The provisioning system creates the A and PTR records of a node and of its BMC.

**R-14.4** The TTL of node records is 300 s. The TTL of service records is 60 s.

**R-14.5** Nodes use the site resolvers. They must not use public resolvers.

**R-14.6** DNSSEC is not used for the internal zones.

**R-14.7** CNAME records for nodes are not allowed. Use the host name.

**R-14.8** The Kubernetes API of a cluster has the name api.<cluster>.<site>.nordlake.internal.

HEL1: resolvers at 10.80.3.53 and 10.80.9.53. The resolvers run PowerDNS Recursor.

HEL2: resolvers at 10.81.3.53 and 10.81.7.53. The resolvers run Knot Resolver.

OUL1: resolvers at 10.88.2.53 and 10.88.6.53. The resolvers run Unbound.

TMP1: resolvers at 10.96.4.53 and 10.96.6.53. The resolvers run Unbound.

ESP1: resolvers at 10.104.1.53 and 10.104.6.53. The resolvers run PowerDNS Recursor.

### 14.1. Record lifecycle

The provisioning system creates the DNS records of a node in the address calculation step (section 16), before the operating system is installed, so that the installer can use the host name. The records of a node that is removed are deleted when the inventory record is closed. The name stays reserved for 90 days (R-4.10), but the record does not exist in that time.

Records that the provisioning system did not create are checked every week. A record without an owner in the inventory system is reported to the site team and deleted after 30 days if nobody claims it.

### 14.2. Names of services

Platform services have names in the zone of their site, for example registry.hel1.nordlake.internal, and a global name in the zone nordlake.internal that points to the nearest site with the service. The global names use the geo-DNS function of the central DNS servers. Tenant services do not get names in the internal zones; the tenants use their own zones.

### 14.3. Split horizon

The internal zones are only visible inside the platform. Tenant workloads use the platform DNS resolvers and can resolve the service names of the platform, but not the names of nodes and BMCs. The resolvers apply a view for this, based on the source address of the query.

### 14.4. Site notes for DNS

HEL1: HEL1 has a third resolver for the provisioning network. The zone hel1.nordlake.internal has about 3000 records.

HEL2: The resolvers of HEL2 are on infra nodes in rack 48. The provisioning system of HEL2 writes records through the DNS API of the central service.

OUL1: The resolvers of OUL1 keep a cache of at most 512 MiB. The provisioning system of OUL1 writes records through the DNS API of the central service.

TMP1: The resolvers of TMP1 keep a cache of at most 512 MiB. Zone transfers for tmp1.nordlake.internal go to the central secondaries in HEL1 and HEL2.

ESP1: ESP1 has a third resolver for the provisioning network. Zone transfers for esp1.nordlake.internal go to the central secondaries in HEL1 and HEL2.

## 15. Time synchronisation

**R-15.1** Each site has two NTP servers with GNSS receivers in the OOB network, at 10.S.0.40 and 10.S.0.41.

**R-15.2** Nodes use chrony with the two NTP servers of their site and the central NTP pool as a fallback.

**R-15.3** The maximum allowed offset of a node is 50 ms. A larger offset creates an alert.

**R-15.4** GPU nodes that run distributed training with PTP use the PTP grandmaster of the hall. The PTP domain is 24.

**R-15.5** Switches use the NTP servers of the site through their management interface.

**R-15.6** Time zone of all nodes and switches: UTC.

### 15.1. PTP

Distributed training on GPU nodes needs a common time with an error of less than 1 microsecond between the nodes of a job. NTP cannot give this. The GPU halls therefore have a PTP grandmaster with a GNSS receiver, and the leaf switches of the GPU racks work as boundary clocks. The nodes run ptp4l on the data ports and phc2sys to set the system clock.

A node that loses the PTP lock falls back to NTP and gets the label ptp-degraded in the cluster, so that the scheduler does not place new training jobs on it.

### 15.2. Site notes for time synchronisation

HEL1: One NTP server of HEL1 uses a rubidium oscillator for holdover. The PTP grandmaster of HEL1 was installed in 2024.

HEL2: The GNSS antennas of HEL2 are on the roof of the provider building and connect through a lightning protection unit. HEL2 has no GPU racks with PTP yet.

OUL1: One NTP server of OUL1 uses a rubidium oscillator for holdover. The PTP boundary clocks of OUL1 are the leaf switches of the GPU racks.

TMP1: The GNSS antennas of TMP1 are on the roof of the provider building and connect through a lightning protection unit. The PTP grandmaster of TMP1 was installed in 2025.

ESP1: One NTP server of ESP1 uses a rubidium oscillator for holdover. The PTP boundary clocks of ESP1 are the leaf switches of the GPU racks.

## 16. Provisioning

The provisioning system takes a node from the inventory record to a running operating system with the platform agent. It uses the rules of sections 4 to 13, 17 and 19 to compute the configuration.

**R-16.1** The inventory record of a node must have the site, the rack, the slot, the role and the serial number before provisioning starts.

**R-16.2** The provisioning system computes the host name (R-4.2), the BMC address (R-6.4), the in-band management address (R-7.2), the VLANs (section 13) and the interface settings (section 11) from the inventory record.

**R-16.3** The provisioning system sets the BMC static address with Redfish, then installs the operating system over the provisioning VLAN.

**R-16.4** After the installation, the provisioning system removes the provisioning VLAN from the leaf ports of the node.

**R-16.5** The node joins the cluster only after the burn-in test passes: 12 hours for compute and storage nodes, 24 hours for GPU nodes.

**R-16.6** A failed burn-in test opens a hardware ticket with the vendor. The node stays in the quarantine pool.

**R-16.7** The provisioning system records each step with a time stamp in the inventory system.

**R-16.8** Reinstallation uses the same steps. The BMC address does not change during a reinstallation.

Table 16-1: Provisioning steps and typical duration

| Step | Typical duration | Can be repeated |
|---|---|---|
| Set BMC address and configuration | 5 min | yes |
| Firmware baseline | 20 to 60 min | yes |
| Operating system installation | 15 min | yes |
| Network configuration | 2 min | yes |
| Burn-in test | 12 or 24 h | yes |
| Cluster join | 5 min | no |

### 16.1. Provisioning steps in detail

#### Inventory check

The provisioning system reads the inventory record and checks that the site, the rack and the slot exist and that the rack purpose in table 3-2 allows the role of the node. A record with a slot that is already in use stops with the error "slot occupied". The site team must correct the record; the provisioning system does not move other nodes.

#### Address calculation

The provisioning system computes all names and addresses of the node in one step and writes them to the inventory record. It uses the general rules and the site deviations of section 19. The values are not computed again in later steps, so that a revision of this standard does not change a node during its provisioning.

#### BMC configuration

The node is connected and powered on with its BMC in DHCP mode. The provisioning system finds the BMC by the MAC address in the inventory record, sets the static BMC address, the gateway and the prefix, and applies the BMC configuration of section 8. It then checks that the BMC answers on the new address.

#### Firmware baseline

The provisioning system updates the BMC, the BIOS, the network cards and the drives to the baseline. A firmware update that needs a cold start uses the PDU outlets of the node.

#### Operating system installation

The node starts from the network over the provisioning VLAN (R-13.4) with HTTP boot. The installer writes the network configuration of section 11 and the VLANs of section 13.

#### Network check

The node sends test traffic on each network to the gateway or, for the storage network, to the storage monitors of the site. The test uses packets of the full interface size without fragmentation, so that a wrong interface setting is found before the node joins the cluster.

#### Burn-in test

The burn-in test loads the CPUs, the memory, the GPUs and the drives. The network part of the test sends traffic between the node and a reference node in another rack on the data and on the storage network.

#### Cluster join

The platform agent registers the node in the cluster of its site with the labels from the inventory record: site, hall, rack, slot and role.

Errors in a step stop the provisioning of the node. The provisioning system writes the error to the inventory record and to the provisioning channel of the site. A step can be repeated after the cause is corrected, except the cluster join (table 16-1).

HEL1: the provisioning servers are in rack 1. A burn-in rack with 8 slots is available for nodes that wait for a rack position.

HEL2: the provisioning servers are in rack 4. There is no separate burn-in rack; burn-in runs in the final position.

OUL1: the provisioning servers are in rack 1. A burn-in rack with 8 slots is available for nodes that wait for a rack position.

TMP1: the provisioning servers are in rack 4. There is no separate burn-in rack; burn-in runs in the final position.

ESP1: the provisioning servers are in rack 3. A burn-in rack with 8 slots is available for nodes that wait for a rack position.

### 16.2. Reinstallation and decommissioning

A reinstallation uses the values that are in the inventory record and does not compute them again, unless the site team asks for a new calculation. A new calculation is necessary after a move of the node and after a revision of this standard that changes a value of the node; the release notes of the provisioning system list these cases.

Decommissioning removes the node from the cluster, wipes the drives with the method of the data handling policy, resets the BMC to the factory settings and closes the inventory record. The site team removes the node from the rack only after the inventory record is closed.

### 16.3. Inventory data quality

Most provisioning errors come from wrong inventory data. The inventory system checks each record when it is saved: the slot must be free, the rack purpose must allow the role, the MAC addresses must be unique and in the format of the vendor, and the serial number must match the delivery note. Records that fail a check cannot be saved.

The site teams compare the inventory records with the racks in the physical audit every six months (section 3.6). Differences are corrected in the inventory system the same day. A node whose record does not match its position must not be provisioned again until the record is correct, because all its names and addresses follow from the record.

### 16.4. Bulk provisioning of a new rack

A new rack with nodes from the factory is provisioned as one batch. The vendor delivers the rack with the nodes installed and cabled to the rack plan. The site team checks the cabling against the plan, connects the rack uplinks and the power, and starts the batch in the provisioning system. The provisioning system runs the steps for all nodes of the rack in parallel, with at most 8 firmware updates at the same time to limit the load on the PDUs.

Before the batch starts, the network automation pipeline configures the OOB switch and the leaf switches of the new rack from the rack number. The VLANs, the subnets and the gateways of the rack follow from the rules of this standard, including the site deviations. The pipeline and the provisioning system use the same rules, so that the switch configuration and the node configuration agree.

### 16.5. Site notes for provisioning

HEL1: The provisioning system of HEL1 keeps the operating system images on a local cache in rack 23. HEL1 provisions most nodes one at a time, because the racks are filled step by step.

HEL2: The provisioning system of HEL2 can install about 80 nodes in parallel. HEL2 provisions most nodes one at a time, because the racks are filled step by step.

OUL1: Firmware images for OUL1 come from the firmware repository mirror on the OOB jump host. The last bulk provisioning at OUL1 was a GPU rack in 2024.

TMP1: Firmware images for TMP1 come from the firmware repository mirror on the OOB jump host. The last bulk provisioning at TMP1 was a GPU rack in 2024.

ESP1: Firmware images for ESP1 come from the firmware repository mirror on the OOB jump host. At ESP1, the vendor delivers racks with the nodes installed.

### 16.6. Known provisioning problems

PROV-301. Problem: the BMC of a new node does not ask for a DHCP address because the vendor delivered it with a static address. Action: the site team resets the BMC network settings from the front panel or with the vendor tool.

PROV-302. Problem: HTTP boot fails on nodes whose BIOS has the network stack disabled. Action: the firmware step enables the network stack; for nodes that skipped the step, enable it in the BIOS setup.

PROV-303. Problem: the operating system installer selects the wrong disk on storage nodes with more than 24 drives. Action: the installer uses the disk by its serial number from the inventory record.

PROV-304. Problem: the burn-in test of GPU nodes fails on the first run after a GPU firmware update. Action: run the burn-in test again; a second failure is a real failure.

PROV-305. Problem: the network check fails when the leaf ports of a new rack are not yet configured. Action: start the batch only after the network automation pipeline reports the rack as ready.

PROV-306. Problem: a node joins the cluster with the wrong rack label when the inventory record was changed during the provisioning. Action: the platform agent reads the labels again every hour and corrects them.

PROV-307. Problem: the firmware step takes longer than 2 hours on nodes with many drives. Action: the timeout of the step is 4 hours for storage nodes.

PROV-308. Problem: the provisioning system cannot reach the BMCs of a new rack because the OOB switch has the factory configuration. Action: the network automation pipeline must configure the OOB switch first.

### 16.7. Provisioning API

Other tools read the results of the provisioning system through its API. The API gives the inventory record of a node with the computed values: the host name, the addresses, the VLANs and the interface settings. Tools must use these values and not compute them again, unless they are the reference implementation of this standard that the provisioning system itself uses.

The API is versioned. A new revision of this standard that changes a computed value is introduced in a new version of the reference implementation first; the provisioning system changes after the tests of the reference implementation pass.

## 17. Storage fabric

The storage network connects the nodes to the Ceph clusters and to the NFS gateways of the site. It is a layer 2 network for each site (R-13.3).

**R-17.1** Each site has one or more Ceph clusters. The Ceph public network is the storage network. The Ceph cluster network is a separate VLAN on the storage nodes only.

**R-17.2** The storage subnet of rack R is 172.(16+n).R.0/24 (R-5.6). The node gets the host octet slot + 20, the same as on the OOB network.

**R-17.3** Storage nodes have two additional 100 Gbit/s ports for the Ceph cluster network.

**R-17.4** The storage network has no gateway. Nodes reach only the storage systems of their own site.

**R-17.5** Quality of service: the storage VLAN uses priority 3 with PFC on the leaf switches. Other VLANs use priority 0.

**R-17.6** OUL1 has its storage systems in the separate storage hall S, about 600 m from hall A. The storage traffic between hall A and hall S runs over the leased DWDM ring of the campus, which also carries the traffic of other tenants. The transponders of the ring do not pass frames larger than 4500 bytes. For this reason the storage interfaces of all nodes at OUL1 are set to 4470 bytes instead of the value that R-11.2 gives. The data interfaces at OUL1 do not use the ring and keep the value of R-11.2.

**R-17.7** The NFS gateways announce their service addresses with BGP (R-10.7) and are reachable from the data network for tenants that cannot use the storage network.

**R-17.8** A change of the storage network that can interrupt Ceph traffic needs a maintenance window of the storage team.

HEL1 has 2 Ceph clusters: ceph-hel1-1 (27 OSD nodes, all-NVMe), ceph-hel1-2 (4 OSD nodes, hybrid). The NFS gateways are in rack 6.

HEL2 has 1 Ceph cluster: ceph-hel2-1 (5 OSD nodes, hybrid). The site has no NFS gateway.

OUL1 has 1 Ceph cluster: ceph-oul1-1 (23 OSD nodes, HDD with NVMe journal). The NFS gateways are virtual machines on the infra nodes.

TMP1 has 3 Ceph clusters: ceph-tmp1-1 (23 OSD nodes, all-NVMe), ceph-tmp1-2 (30 OSD nodes, HDD with NVMe journal), ceph-tmp1-3 (15 OSD nodes, HDD with NVMe journal). The NFS gateways are virtual machines on the infra nodes.

ESP1 has 1 Ceph cluster: ceph-esp1-1 (21 OSD nodes, HDD with NVMe journal). The site has no NFS gateway.

### 17.1. Ceph network layout

Ceph clients on the nodes connect to the monitors and to the OSDs through the storage network. The OSD nodes use their storage interfaces for the client traffic and their additional ports for the replication traffic between the OSDs (R-17.3). This keeps the replication traffic, which can be several times the client traffic during a recovery, away from the leaf ports of the client nodes.

The monitors of a Ceph cluster are on three storage nodes in three different racks. Each monitor address is a fixed address in the storage subnet of its rack. The client configuration on the nodes lists the three monitor addresses; the platform agent updates the list when a monitor moves.

### 17.2. NFS gateways

NFS gateways export CephFS to tenants that cannot use the Ceph client, for example old applications in virtual machines. They are on the data network and on the storage network. The service addresses are announced with BGP (R-17.7). The gateways run in pairs, and the service address moves to the other gateway of the pair in a failure.

### 17.3. Storage performance tests

After a change of the storage network, the storage team runs the standard performance test from three client nodes in different racks. The test writes and reads with large blocks and with small blocks, and compares the results with the last test of the same site. A difference of more than 15 % stops the change and the change is rolled back, unless the storage team accepts the new values.

### 17.4. Site notes for the storage fabric

HEL1: The storage monitors of HEL1 are in racks 11, and two other storage racks. The last performance test at HEL1 was in 2024.

HEL2: HEL2 has a separate Ceph cluster for backups. At HEL2, the storage traffic is about 40 % of the fabric traffic.

OUL1: The Ceph dashboards of OUL1 are on the infra nodes. The last performance test at OUL1 was in 2026.

TMP1: The Ceph dashboards of TMP1 are on the infra nodes. The storage team of TMP1 plans to add 6 OSD nodes next year.

ESP1: The storage monitors of ESP1 are in racks 11, and two other storage racks. At ESP1, the storage traffic is about 90 % of the fabric traffic.

## 18. Security zones

**R-18.1** The platform has four security zones: management, platform, tenant and border.

**R-18.2** The OOB network and the in-band management network are in the management zone.

**R-18.3** The data network is in the tenant zone, except for the platform service addresses, which are in the platform zone.

**R-18.4** Traffic between zones goes through the firewall cluster of the site. The default rule is deny.

**R-18.5** Firewall rules are kept in the firewall policy repository and reviewed every six months.

**R-18.6** Administrators reach the management zone only through the bastion hosts with hardware tokens.

**R-18.7** BMC access from the bastion hosts is allowed only to the HTTPS and SSH ports of the BMCs.

**R-18.8** The storage network is not routed and therefore has no firewall. Access control is in Ceph.

**R-18.9** Each security event of the firewall cluster goes to the security monitoring system within 60 s.

### 18.1. Allowed flows between zones

The list gives the flows that the firewall clusters allow between the zones. A flow that is not on the list is denied (R-18.4). The list is the same for all sites, unless section 19 says otherwise.

- F-01: from bastion hosts (management zone) to Kubernetes API of all clusters (platform zone), TCP 6443.
- F-02: from bastion hosts (management zone) to BMCs (management zone), TCP 443, TCP 22.
- F-03: from provisioning servers (management zone) to BMCs (management zone), TCP 443.
- F-04: from hardware exporter (management zone) to BMCs (management zone), TCP 443.
- F-05: from BMCs (management zone) to site syslog server (management zone), TCP 6514.
- F-06: from BMCs (management zone) to site NTP servers (management zone), UDP 123.
- F-07: from OOB jump host (management zone) to firmware repository mirror (management zone), TCP 443.
- F-08: from Prometheus (platform zone) to node exporters (management zone), TCP 9100.
- F-09: from Prometheus (platform zone) to platform agents (management zone), TCP 9469.
- F-10: from nodes (management zone) to registry mirror (platform zone), TCP 443.
- F-11: from nodes (management zone) to package mirror (platform zone), TCP 443.
- F-12: from nodes (management zone) to log aggregators (platform zone), TCP 6000.
- F-13: from tenant workloads (tenant zone) to platform DNS resolvers (platform zone), UDP 53, TCP 53.
- F-14: from tenant workloads (tenant zone) to platform API (platform zone), TCP 443.
- F-15: from tenant workloads (tenant zone) to internet through the egress proxy (border zone), TCP 3128.
- F-16: from internet (border zone) to tenant load balancer addresses (tenant zone), TCP 80, TCP 443.
- F-17: from partner networks (border zone) to platform API (platform zone), TCP 443.
- F-18: from certificate service (platform zone) to public ACME servers through the egress proxy (border zone), TCP 3128.
- F-19: from bastion hosts (management zone) to vendor support portals through the egress proxy (border zone), TCP 3128.
- F-20: from load balancer nodes (platform zone) to leaf switches (platform zone), TCP 179.
- F-21: from network automation (management zone) to switch management ports (management zone), TCP 22, TCP 57400.
- F-22: from network automation (management zone) to PDUs (management zone), TCP 443, UDP 161.
- F-23: from console aggregation (management zone) to console servers (management zone), TCP 22.
- F-24: from backup service (platform zone) to etcd of the control plane nodes (platform zone), TCP 2379.

Temporary flows for a project need a normal change and an end date of at most 90 days. The firewall policy repository removes a temporary flow on its end date.

### 18.2. Access reviews

The security team reviews the members of the groups with access to the management zone every quarter. The managers of the members confirm that the access is still necessary. Access that is not confirmed is removed at the end of the review.

### 18.3. Logging of administrative access

All sessions through the bastion hosts are recorded. The recordings are kept for 12 months. The security team can search the recordings by user, by target host and by time. Commands that change the configuration of a node outside configuration management create an alert for the team that owns the node.

### 18.4. Vulnerability management

The security team scans the management zone every week. Findings on BMCs, switches and PDUs go to the site teams with a due date that depends on the severity: 7 days for critical, 30 days for high and 90 days for other findings. Findings that need a firmware version that is not yet in the baseline are handled by the firmware baseline process (R-8.1).

### 18.5. Break-glass procedure

When the bastion hosts of a site are not available, the duty manager can open break-glass access. The person on call then connects to the OOB jump host of the site with a hardware token and a one-time password from the vault. Each break-glass session is recorded, and the security team reviews the recording within two working days. The access ends after 8 hours or when the bastion hosts work again.

## 19. Site deviations

This section lists the approved deviations from the general rules. Each deviation names the rule that it changes. A deviation takes precedence over the general rule (R-1.4). Deviations that are withdrawn stay in the list with the mark "withdrawn"; they do not apply.

**R-19.1** HEL1: racks 47 and 48 are in the network room and contain only network equipment. The provisioning system must reject nodes in these racks.

**R-19.2** HEL1: the console servers are in every rack, not in every fourth rack as R-3.3 says, because of the old cable layout of building 2.

**R-19.3** HEL2: the site has 8 spines instead of 4 (R-9.3), because of the size of the site.

**R-19.4** HEL2: hall B (racks 41 to 64) has its own OOB aggregation switch pair, hel2-oobagg-b1 and hel2-oobagg-b2. The OOB subnets of the racks in hall B do not follow R-6.3: the OOB subnet of rack R in hall B is 10.17.(100 + R).0/24. In this subnet the host octets follow R-6.4 and the gateway is .1 as R-6.5 says. Example: the node in HEL2, rack 45, slot 3 has the BMC address 10.17.145.23 and the gateway 10.17.145.1. The racks 1 to 40 in hall A of HEL2 use the general rules.

**R-19.5** HEL2: hall B has its own PTP grandmaster. The PTP domain in hall B is 25 instead of 24 (R-15.4).

**R-19.6** OUL1: the storage hall S contains racks 29 to 32. Only storage nodes are allowed in these racks.

**R-19.7** OUL1: the remote hands service is not available on public holidays. Plan hardware work on other days.

**R-19.8** OUL1: the storage interfaces of the nodes use a smaller frame size than R-11.2 gives, because of the leased ring between hall A and hall S. R-17.6 gives the value and the reason.

**R-19.9** TMP1: the site resolvers are in the central DNS service of the campus provider and not in the infra racks (R-14.2). The provider gives the addresses.

**R-19.10** TMP1 (withdrawn in revision 13, does not apply): the BMC host octet was the slot plus 30, because the old console servers used the addresses up to .29. The old console servers were removed in 2025 and TMP1 now uses R-6.4.

**R-19.11** ESP1: the colocation provider does not allow liquid-cooled racks. GPU nodes at ESP1 use air cooling and the limit of 17 kW per rack (R-3.6).

**R-19.12** ESP1: the provider network team operates the site routers. The border leaf pair peers with the provider routers with eBGP and the provider ASN 4210099000.

**R-19.13** ESP1: the NTP servers are in the provider network. The addresses in R-15.1 are NAT addresses for them.

## 20. Monitoring

**R-20.1** Each node runs the node exporter and the platform agent. Prometheus scrapes them over the in-band management network every 30 s.

**R-20.2** Switches are monitored with gNMI streaming telemetry. SNMP is only used for the PDUs.

**R-20.3** BMC sensors are read through Redfish every 5 minutes by the hardware exporter of the site.

**R-20.4** Alerts go to the on-call rotation of the team that owns the component. The ownership is in the service catalogue.

**R-20.5** Interface errors: an alert starts when a port has more than 100 CRC errors in 5 minutes.

**R-20.6** Optical levels: an alert starts when the receive level of a transceiver is less than 2 dB above the low alarm threshold.

**R-20.7** Monitoring data is kept for 30 days at full resolution and for 13 months as 1-hour averages.

Table 20-1: Alert thresholds

| Metric | Warning | Critical | Owner |
|---|---|---|---|
| Node CPU temperature | 85 C | 95 C | site team |
| GPU temperature | 88 C | 95 C | site team |
| Inlet air temperature | 27 C | 32 C | facility |
| PDU load per phase | 70 % | 85 % | site team |
| Leaf port utilisation (15 min) | 70 % | 90 % | network |
| BMC not reachable | 15 min | 60 min | site team |
| NTP offset | 20 ms | 50 ms | platform |
| Ceph OSD down | 1 | 3 | storage |
| Disk SMART pre-fail | 1 | - | site team |
| Fan failure | 1 | 2 in one node | site team |

### 20.1. Runbook summaries

The full runbooks are in the operations wiki. The summaries give the first actions, so that the person on call can start without the wiki when the in-band management network is down.

#### BMC not reachable

Check the OOB switch port of the slot of the node. If the port is down, check the cable and the BMC link LED. If the port is up, restart the BMC through the PDU outlets of the node only when the node is drained; a power cycle stops the node.

#### Leaf switch down

The nodes of the rack continue on the other leaf. Do not drain the nodes. Check the console of the switch through the console server of the rack group. Open a hardware case if the switch does not start.

#### Both leaf switches of a rack down

Drain the nodes of the rack in the cluster. Check the power of the rack and the PDUs. Inform the tenants of the rack through the status page.

#### Spine down

No action on the nodes. Check the optical levels of the links to the spine. A second spine down in the same site is a major incident.

#### Storage network errors

Check the CRC counters on the leaf ports of the storage nodes. A large number of drops without CRC errors can mean that the interface size of a node is wrong; compare the node settings with section 11 and the site deviations.

#### NTP offset

Check that the NTP servers of the site have a GNSS lock. If both servers lost the lock, the nodes use the central pool; no action is needed for 24 hours.

#### Inlet temperature

Check the cooling units of the hall with the facility team. If the critical threshold is reached, drain and power off GPU nodes in the hottest racks first.

#### PDU load per phase

Check for new nodes in the rack that are not in the power budget of table 3-2. Move power supplies between phases only in a change window.

#### Ceph OSD down

The storage team owns the alert. The site team checks the drive LEDs and the storage interface of the node when the storage team asks.

#### Fan failure

Open a hardware case. For GPU nodes with air cooling, drain the node when two fans fail.

#### Provisioning stopped

Read the error in the inventory record. Most errors are wrong inventory data: a wrong slot, a wrong MAC address or a rack purpose that does not allow the role.

#### Optical levels low

Clean the connectors at both ends (R-12.9). Replace the transceiver if the level stays low.

### 20.2. On-call

Each site team has an on-call rotation for the hardware and the network of the site. The platform team, the storage team and the network team have their own rotations. The person on call of the site team is the first contact for alerts of the site; the other teams join when their components are involved. A major incident is declared by the duty manager, who then leads the incident.

### 20.3. Dashboards

Each site has a set of standard dashboards: the site overview, the rack view, the OOB rack view, the fabric view and the storage view. The rack view shows for each rack the power load, the inlet temperature, the state of the leaf switches and the state of each node. The OOB rack view shows the state of each address of the OOB subnet of the rack, so that the site team can see a missing BMC or a missing PDU at once.

### 20.4. Capacity reports

The monitoring system makes a capacity report for each site every month: the power load of each rack against its budget, the free slots, the use of the leaf uplinks and the free addresses in the service pools. The site teams use the report to plan new racks, and the Platform Architecture Board uses it to plan new sites.

## 21. Change control

**R-21.1** Each change of the network or of a node position needs a change record with a risk class: standard, normal or emergency.

**R-21.2** Standard changes are pre-approved. The list of standard changes is in the change catalogue.

**R-21.3** Normal changes need an approval of the change advisory board, which meets every Tuesday.

**R-21.4** Emergency changes need the approval of the duty manager and a review within 5 working days.

**R-21.5** A change of this standard is a normal change. The new revision gets the next revision number and an entry in appendix D.

**R-21.6** Tools that implement this standard must be updated within 30 days after a new revision is approved.

### 21.1. Standard changes

- SC-01: Add a node in a free slot of a rack whose purpose allows the role.
- SC-02: Remove a node that is drained and in the quarantine pool.
- SC-03: Replace a failed drive, fan, power supply or memory module.
- SC-04: Replace a transceiver or a patch cable with the same type.
- SC-05: Update firmware to the current baseline on drained nodes.
- SC-06: Restart a BMC.
- SC-07: Add a DNS record for a service address from the pool.
- SC-08: Add a temporary flow from the catalogue of pre-approved flows.
- SC-09: Update the serial number of a device in the inventory system.
- SC-10: Rotate a BMC password.

## Appendix A: Lessons learned

This appendix gives short summaries of incidents that led to a change of this standard. The full reports are in the incident system.

### Address pools without structure (2019)

At HEL1, addresses came from pools. During a power incident, the site team could not find the failed devices from the alert addresses without the inventory system, which was itself down. The address plan of section 5 was the result.

### Shared LOM ports (2020)

A node model with shared LOM ports answered ARP requests for the host address from the BMC. The rule to disable the shared LOM port (R-8.13) was the result.

### Wrong rack position in the inventory (2022)

A node was installed in slot 12 but recorded in slot 14. It got the addresses of slot 14, and the BMC of the real node in slot 14 had an address conflict. The rule that the inventory record is the input of all addressing (R-3.13) was made stricter, and the network check of the provisioning now compares the LLDP neighbour port with the slot.

### Large frames on a leased path (2025)

A storage path through a leased transmission system did not pass large frames. Ping and small reads worked, but large writes stopped. It took two days to find the cause. The network check in the provisioning now sends packets of the full interface size.

### Rack infrastructure addresses (2025)

New PDUs with two management cards needed more addresses than the old reservation at the start of each OOB subnet gave. The reservation was made larger in revision 12.

### 21.2. Change calendar

The change calendar shows all approved changes. Changes that affect the same site, the same hall or the same service must not overlap, unless the change advisory board approves it. The maintenance windows of the sites are on Tuesday and Thursday nights from 22 to 04 local time. The calendar is frozen from 15 December to 6 January, except for emergency changes.

### 21.3. Revision process for this standard

A change request for this standard describes the problem, the proposed change of the rules and the effect on the tools that implement the standard. Platform Network Engineering writes the new text, and the Platform Architecture Board approves it. The new revision gets an entry in appendix D. The owners of the tools get a notification and must update their tools within 30 days (R-21.6).

## Appendix B: Design decisions

The design decisions give the reasons for the main choices in this standard. They do not add rules.

### D-1: One fabric for data and storage

A separate storage fabric was used at HEL1 until 2021. It doubled the number of leaf switches and the cabling, and the storage fabric was used at less than 20 % on average. One fabric with a priority class for storage traffic (R-17.5) gives the same performance at a lower cost. The risk is that a fabric failure stops both networks; the fabric design (section 9.2) limits this risk.

### D-2: EVPN multihoming instead of MLAG

MLAG pairs need a peer link and have failure modes in which both switches think that they are the primary. EVPN multihoming has no peer link and uses the standard EVPN routes for the redundancy. All new leaf switches support it.

### D-3: Addresses from the rack position

Addresses that follow from the rack position make it possible to find a device without the inventory system. The cost is that a node move changes its addresses. Node moves are rare, and the provisioning system handles them (section 6.2).

### D-4: Static BMC addresses

DHCP for BMCs would make the address assignment easier, but it makes the BMC access depend on the DHCP service. The BMC access is the last access to a node in an incident, so it must not depend on another service. DHCP is only used for the first start (R-6.6).

### D-5: No IPv6 on nodes yet

The platform services and some tenant applications do not support IPv6. The IPv6 plan (draft NCP-NET-STD-009) will add IPv6 to the data network first.

### D-6: Private ASNs from a formula

A registry of ASNs was used before revision 6 and had errors. A formula (R-10.2) cannot be wrong for one rack only, and the automation can compute it.

### D-7: LACP bonds with VLAN subinterfaces

Separate ports for data and storage would need four ports for each node. Two ports with VLAN subinterfaces give the redundancy with half of the cables and leaf ports.

### D-8: Site deviations in one section

Deviations were written into the general rules in the early revisions, and tools missed some of them. Since revision 9, all deviations are in section 19, and each deviation names the rule that it changes.

### D-9: Firmware baseline per quarter

A monthly baseline was too much work for the site teams, and a yearly baseline left known security problems open for too long. A quarterly baseline with an exception process for critical security fixes is the compromise.

### D-10: Burn-in in the final position

A separate burn-in area needs a second cabling of each node. Burn-in in the final position tests the real cabling, and a failed node is replaced in the same position.

## Appendix C: Leaf switch inventory

One row for each leaf pair, from the inventory system on the date of this revision. The ASN follows R-10.2 and is listed here for the convenience of the site teams.

### C.1. HEL1

| Leaf pair | Rack | ASN | Model | NOS version | Serial a | Serial b |
|---|---|---|---|---|---|---|
| hel1-leaf-r01a/b | 1 | 4210016001 | LEAF-64D | 4.32.2F | TG05EGLM6X | ERY49EERY8 |
| hel1-leaf-r02a/b | 2 | 4210016002 | LEAF-32D | 4.32.2F | 110Y7Y7MUU | S8ZZUE2578 |
| hel1-leaf-r03a/b | 3 | 4210016003 | LEAF-32D | 4.32.2F | NBG9YH93H8 | 2PT9EGWG6B |
| hel1-leaf-r04a/b | 4 | 4210016004 | LEAF-64D | 4.32.2F | C3NKL103PM | S1FULAFKRC |
| hel1-leaf-r05a/b | 5 | 4210016005 | LEAF-64D | 4.33.1F | T7EDX8M08G | XT0K6C3ECS |
| hel1-leaf-r06a/b | 6 | 4210016006 | LEAF-64D | 4.33.1F | 7VZ9SDCZSS | 6EP6ZB4HVR |
| hel1-leaf-r07a/b | 7 | 4210016007 | LEAF-32D | 4.32.2F | Y1C4K8AR6M | 0X107V5WSS |
| hel1-leaf-r08a/b | 8 | 4210016008 | LEAF-32D | 4.32.2F | UY0275BDA8 | 50YLKGGG58 |
| hel1-leaf-r09a/b | 9 | 4210016009 | LEAF-32D | 4.32.2F | U1EKUZRW1W | UTY4AJ3SPE |
| hel1-leaf-r10a/b | 10 | 4210016010 | LEAF-32D | 4.33.1F | AFKR8EP4CH | H85GGUW9WF |
| hel1-leaf-r11a/b | 11 | 4210016011 | LEAF-32D | 4.32.2F | 2423NYWS6C | 78EMJMC2UP |
| hel1-leaf-r12a/b | 12 | 4210016012 | LEAF-32D | 4.32.2F | H588FP2ZBA | J49MG42XBU |
| hel1-leaf-r13a/b | 13 | 4210016013 | LEAF-32D | 4.32.2F | GH3NTZ4H93 | LMD402EKHL |
| hel1-leaf-r14a/b | 14 | 4210016014 | LEAF-32D | 4.33.1F | 6JC5F8S7S8 | 9WCHJZK0U8 |
| hel1-leaf-r15a/b | 15 | 4210016015 | LEAF-32D | 4.33.1F | 49XSEEN401 | K45AWX9PJY |
| hel1-leaf-r16a/b | 16 | 4210016016 | LEAF-64D | 4.32.2F | JW1PL2XVFR | N7Z611SWC5 |
| hel1-leaf-r17a/b | 17 | 4210016017 | LEAF-64D | 4.32.2F | 8WZ5D7KMEF | JGYN93KHVD |
| hel1-leaf-r18a/b | 18 | 4210016018 | LEAF-32D | 4.32.2F | 60RXTVC11S | N1R6ZZVTG1 |
| hel1-leaf-r19a/b | 19 | 4210016019 | LEAF-32D | 4.33.1F | 4WMFRC56HN | V4TXYL2MKD |
| hel1-leaf-r20a/b | 20 | 4210016020 | LEAF-32D | 4.32.2F | WVHF8R9SXE | F91U9CRWHC |
| hel1-leaf-r21a/b | 21 | 4210016021 | LEAF-32D | 4.33.1F | X24FHFH83G | KPG8NRDAK4 |
| hel1-leaf-r22a/b | 22 | 4210016022 | LEAF-32D | 4.32.2F | U3BTE7HXF7 | N51U6F22SY |
| hel1-leaf-r23a/b | 23 | 4210016023 | LEAF-32D | 4.32.2F | PDHEZ5XPMX | VCRVAAULPZ |
| hel1-leaf-r24a/b | 24 | 4210016024 | LEAF-32D | 4.33.1F | DH009EKUDA | M0B96Y9W3L |
| hel1-leaf-r25a/b | 25 | 4210016025 | LEAF-32D | 4.32.2F | C15BTC4HCP | 7DBB70K45K |
| hel1-leaf-r26a/b | 26 | 4210016026 | LEAF-32D | 4.32.2F | HR5RLLJVRV | JBLA53XTMJ |
| hel1-leaf-r27a/b | 27 | 4210016027 | LEAF-64D | 4.33.1F | C0SH9ESP14 | S437TWLTU9 |
| hel1-leaf-r28a/b | 28 | 4210016028 | LEAF-32D | 4.33.1F | 8V8EPU87VE | 94545NPLGR |
| hel1-leaf-r29a/b | 29 | 4210016029 | LEAF-64D | 4.32.2F | 8NH5U0LX2U | 4RSWSMUJ6B |
| hel1-leaf-r30a/b | 30 | 4210016030 | LEAF-64D | 4.32.2F | LLH986WKC1 | 2533U3C829 |
| hel1-leaf-r31a/b | 31 | 4210016031 | LEAF-64D | 4.32.2F | NMRXNK3KVW | F3CJE72TNJ |
| hel1-leaf-r32a/b | 32 | 4210016032 | LEAF-64D | 4.33.1F | 50NBMB5TUG | MJU304NPBW |
| hel1-leaf-r33a/b | 33 | 4210016033 | LEAF-32D | 4.32.2F | VMS1H8D46H | FP8RVNJFU5 |
| hel1-leaf-r34a/b | 34 | 4210016034 | LEAF-64D | 4.33.1F | 4W3YH05UNU | 8PWYMLJFBE |
| hel1-leaf-r35a/b | 35 | 4210016035 | LEAF-32D | 4.32.2F | ESXXH3PSSB | 5G81US7SB6 |
| hel1-leaf-r36a/b | 36 | 4210016036 | LEAF-32D | 4.33.1F | W2PV9432DP | 9JTPXELRY2 |
| hel1-leaf-r37a/b | 37 | 4210016037 | LEAF-32D | 4.32.2F | J8BSFDHCEV | WU2KJM29B4 |
| hel1-leaf-r38a/b | 38 | 4210016038 | LEAF-32D | 4.32.2F | 5FZM2A6HDM | S7LYFD61FR |
| hel1-leaf-r39a/b | 39 | 4210016039 | LEAF-64D | 4.32.2F | JPERGNCC8V | J5FA8G1AN1 |
| hel1-leaf-r40a/b | 40 | 4210016040 | LEAF-64D | 4.32.2F | DG8RBKHW4V | 1ERSG8MZ32 |
| hel1-leaf-r41a/b | 41 | 4210016041 | LEAF-64D | 4.33.1F | 96DJ5XCKEZ | 5GNEFCJ8D5 |
| hel1-leaf-r42a/b | 42 | 4210016042 | LEAF-64D | 4.33.1F | KBJCNBCU36 | 57NE7A4P7R |
| hel1-leaf-r43a/b | 43 | 4210016043 | LEAF-32D | 4.32.2F | 9V1MPLE570 | XRCGPPUD8G |
| hel1-leaf-r44a/b | 44 | 4210016044 | LEAF-32D | 4.32.2F | GZFVPN1N1X | VHBLCF8P9Y |
| hel1-leaf-r45a/b | 45 | 4210016045 | LEAF-32D | 4.32.2F | VZ1ZZU4TD8 | NYM3W7J88S |
| hel1-leaf-r46a/b | 46 | 4210016046 | LEAF-64D | 4.32.2F | S68SB7DN70 | 3FGGAUH0EU |

### C.2. HEL2

| Leaf pair | Rack | ASN | Model | NOS version | Serial a | Serial b |
|---|---|---|---|---|---|---|
| hel2-leaf-r01a/b | 1 | 4210017001 | LEAF-32D | 4.33.1F | LU0TF2CRC5 | 6VY5533Y3F |
| hel2-leaf-r02a/b | 2 | 4210017002 | LEAF-32D | 4.32.2F | UMP9D32RMH | KKWYY9YF6T |
| hel2-leaf-r03a/b | 3 | 4210017003 | LEAF-32D | 4.32.2F | 8ZPMRR3CMV | 6VN60C82SJ |
| hel2-leaf-r04a/b | 4 | 4210017004 | LEAF-64D | 4.32.2F | 6KPF11GAGM | VPZPG0SJJD |
| hel2-leaf-r05a/b | 5 | 4210017005 | LEAF-32D | 4.33.1F | CCCKFXS35Y | N93RN6VK3L |
| hel2-leaf-r06a/b | 6 | 4210017006 | LEAF-32D | 4.33.1F | FLX7DBKURX | 3NYUPAD9G9 |
| hel2-leaf-r07a/b | 7 | 4210017007 | LEAF-32D | 4.32.2F | GXS5903172 | LCY8AGGVY6 |
| hel2-leaf-r08a/b | 8 | 4210017008 | LEAF-32D | 4.32.2F | D68L9R3C8L | APFLKEGLX1 |
| hel2-leaf-r09a/b | 9 | 4210017009 | LEAF-64D | 4.32.2F | W8RK003PDZ | K961FX1RJG |
| hel2-leaf-r10a/b | 10 | 4210017010 | LEAF-32D | 4.32.2F | JFNAP5PWHP | LEBXPUJS1Y |
| hel2-leaf-r11a/b | 11 | 4210017011 | LEAF-32D | 4.33.1F | WD996DR1YA | U2C1W8M343 |
| hel2-leaf-r12a/b | 12 | 4210017012 | LEAF-32D | 4.32.2F | 4WNM0FD6VV | XZUZ2Y60EC |
| hel2-leaf-r13a/b | 13 | 4210017013 | LEAF-64D | 4.33.1F | UCXMFAZ7MJ | JKZAARDVWU |
| hel2-leaf-r14a/b | 14 | 4210017014 | LEAF-32D | 4.32.2F | TCY322WXHZ | 375C7WRLDC |
| hel2-leaf-r15a/b | 15 | 4210017015 | LEAF-64D | 4.33.1F | SRPNUN652F | XGJ9ULUECF |
| hel2-leaf-r16a/b | 16 | 4210017016 | LEAF-32D | 4.32.2F | W199AEEAFK | HXEJ8D3A2Y |
| hel2-leaf-r17a/b | 17 | 4210017017 | LEAF-32D | 4.32.2F | DWTGSF46WX | DZ247XVNLL |
| hel2-leaf-r18a/b | 18 | 4210017018 | LEAF-64D | 4.32.2F | GTMSDW5UDR | LBYL9938TJ |
| hel2-leaf-r19a/b | 19 | 4210017019 | LEAF-32D | 4.32.2F | 79Z9VNGFZN | 36WT8XYS63 |
| hel2-leaf-r20a/b | 20 | 4210017020 | LEAF-64D | 4.33.1F | TA8GBLYR40 | F7XFBH2WMD |
| hel2-leaf-r21a/b | 21 | 4210017021 | LEAF-64D | 4.32.2F | RLDAMRB7NL | X7J5CESNLK |
| hel2-leaf-r22a/b | 22 | 4210017022 | LEAF-32D | 4.32.2F | RH94R168E2 | 1V6SG9RTCG |
| hel2-leaf-r23a/b | 23 | 4210017023 | LEAF-32D | 4.32.2F | F0CKY69RNZ | 9Z2M22GW50 |
| hel2-leaf-r24a/b | 24 | 4210017024 | LEAF-32D | 4.33.1F | X9J2TSBKCN | MF9AJDJCGJ |
| hel2-leaf-r25a/b | 25 | 4210017025 | LEAF-32D | 4.32.2F | RC27X9EES3 | NLZ37Z4DBV |
| hel2-leaf-r26a/b | 26 | 4210017026 | LEAF-32D | 4.33.1F | R3DB2FLUHE | BERMLRXWT9 |
| hel2-leaf-r27a/b | 27 | 4210017027 | LEAF-32D | 4.33.1F | EH3AAH16R4 | EWWYVSGXUM |
| hel2-leaf-r28a/b | 28 | 4210017028 | LEAF-32D | 4.32.2F | S4WUTGYJFU | 9DSY88MVK5 |
| hel2-leaf-r29a/b | 29 | 4210017029 | LEAF-32D | 4.33.1F | 07LM2A5Z93 | 9NJKG30S4N |
| hel2-leaf-r30a/b | 30 | 4210017030 | LEAF-32D | 4.32.2F | 0BDUMPLHVF | 2BUKYFJ65W |
| hel2-leaf-r31a/b | 31 | 4210017031 | LEAF-32D | 4.32.2F | 9AG5CDMS8U | 5EBT45JMSC |
| hel2-leaf-r32a/b | 32 | 4210017032 | LEAF-32D | 4.32.2F | N9WNHDPSRC | HGRJ7ZT3HT |
| hel2-leaf-r33a/b | 33 | 4210017033 | LEAF-32D | 4.32.2F | AXZLD2DRSU | TP5GLYDNXR |
| hel2-leaf-r34a/b | 34 | 4210017034 | LEAF-32D | 4.33.1F | 0EAXKUP2Y5 | 14XCETUGCK |
| hel2-leaf-r35a/b | 35 | 4210017035 | LEAF-32D | 4.33.1F | 41L6JPFPE9 | GUZ7EDWZM6 |
| hel2-leaf-r36a/b | 36 | 4210017036 | LEAF-32D | 4.33.1F | 0KHV418W7A | X2FL6RAYF9 |
| hel2-leaf-r37a/b | 37 | 4210017037 | LEAF-32D | 4.33.1F | 6LVJJ0PAXG | C010CBWXNL |
| hel2-leaf-r38a/b | 38 | 4210017038 | LEAF-64D | 4.32.2F | 5HU7EA88NR | G0672208KM |
| hel2-leaf-r39a/b | 39 | 4210017039 | LEAF-32D | 4.33.1F | UELCRUNCDA | 0DKEJLVBC2 |
| hel2-leaf-r40a/b | 40 | 4210017040 | LEAF-32D | 4.32.2F | 1SX63G8HV8 | 2WZWP87JU1 |
| hel2-leaf-r41a/b | 41 | 4210017041 | LEAF-32D | 4.33.1F | P51S3XY5WV | BHNW9VW8HL |
| hel2-leaf-r42a/b | 42 | 4210017042 | LEAF-32D | 4.32.2F | N4W9HUL2RT | 9WZWR6TZ6A |
| hel2-leaf-r43a/b | 43 | 4210017043 | LEAF-32D | 4.33.1F | WG4ZZZ63E3 | YK67L0CZBJ |
| hel2-leaf-r44a/b | 44 | 4210017044 | LEAF-64D | 4.32.2F | 9D375LEBFN | 957B2X05ZK |
| hel2-leaf-r45a/b | 45 | 4210017045 | LEAF-64D | 4.33.1F | H3GGP16U8R | E9L2SP93MH |
| hel2-leaf-r46a/b | 46 | 4210017046 | LEAF-32D | 4.32.2F | VDTJPRVZ12 | NPEKMBLBPL |
| hel2-leaf-r47a/b | 47 | 4210017047 | LEAF-32D | 4.32.2F | CUDMZ9WCS8 | 0581N7EVUV |
| hel2-leaf-r48a/b | 48 | 4210017048 | LEAF-64D | 4.33.1F | XKWKAAACY1 | ZH2H2XYKSP |
| hel2-leaf-r49a/b | 49 | 4210017049 | LEAF-64D | 4.32.2F | 7E0G91ZCUB | CV318P29XH |
| hel2-leaf-r50a/b | 50 | 4210017050 | LEAF-32D | 4.33.1F | 9K6ASJ2XYR | 80P3U4YKV1 |
| hel2-leaf-r51a/b | 51 | 4210017051 | LEAF-32D | 4.32.2F | ETVLJJZ9YW | SS1DPT9KJC |
| hel2-leaf-r52a/b | 52 | 4210017052 | LEAF-32D | 4.32.2F | KVVP1F0WHV | SCF81UM1T0 |
| hel2-leaf-r53a/b | 53 | 4210017053 | LEAF-64D | 4.32.2F | DKHRAJP1JN | MZTL4RHHCD |
| hel2-leaf-r54a/b | 54 | 4210017054 | LEAF-64D | 4.32.2F | 8TFVJXXP0S | SM1HZLZRXZ |
| hel2-leaf-r55a/b | 55 | 4210017055 | LEAF-32D | 4.32.2F | AYP1E9LBE7 | U5KVETJGYH |
| hel2-leaf-r56a/b | 56 | 4210017056 | LEAF-32D | 4.32.2F | 4U73GLZ9TF | 11PB981SPW |
| hel2-leaf-r57a/b | 57 | 4210017057 | LEAF-64D | 4.33.1F | D487HT6L9C | 2BBDXXLVCV |
| hel2-leaf-r58a/b | 58 | 4210017058 | LEAF-32D | 4.32.2F | JTATFL3HEH | 8J8A09C818 |
| hel2-leaf-r59a/b | 59 | 4210017059 | LEAF-32D | 4.33.1F | Y9GVGZ5P7B | L5JKH7YPGZ |
| hel2-leaf-r60a/b | 60 | 4210017060 | LEAF-32D | 4.33.1F | H6Z0MYEL4D | CLG14FUU46 |
| hel2-leaf-r61a/b | 61 | 4210017061 | LEAF-32D | 4.33.1F | CJPYTUMCE2 | ZAD3UAABLA |
| hel2-leaf-r62a/b | 62 | 4210017062 | LEAF-32D | 4.32.2F | 3NDJMZKC1F | F28S4B5JTU |
| hel2-leaf-r63a/b | 63 | 4210017063 | LEAF-64D | 4.32.2F | R1JVUMW0YJ | VFSYG8MX8M |
| hel2-leaf-r64a/b | 64 | 4210017064 | LEAF-32D | 4.32.2F | 1S5ZVTKHU7 | XYDRL6783L |

### C.3. OUL1

| Leaf pair | Rack | ASN | Model | NOS version | Serial a | Serial b |
|---|---|---|---|---|---|---|
| oul1-leaf-r01a/b | 1 | 4210024001 | LEAF-32D | 4.32.2F | N7AE7X8PYW | JN7BR740WN |
| oul1-leaf-r02a/b | 2 | 4210024002 | LEAF-32D | 4.33.1F | DBKW0DE09C | 7C41JPH9UG |
| oul1-leaf-r03a/b | 3 | 4210024003 | LEAF-32D | 4.33.1F | HXAVXKTMFG | URHV3GX2JP |
| oul1-leaf-r04a/b | 4 | 4210024004 | LEAF-32D | 4.32.2F | MWJPXVKB7X | RKCCLVL13E |
| oul1-leaf-r05a/b | 5 | 4210024005 | LEAF-32D | 4.32.2F | 027VSBYJBY | B54MK7UMGP |
| oul1-leaf-r06a/b | 6 | 4210024006 | LEAF-32D | 4.32.2F | SPP736TCK7 | GKPB5G07DC |
| oul1-leaf-r07a/b | 7 | 4210024007 | LEAF-32D | 4.33.1F | 33AA5S0ZY0 | VLRYVAF134 |
| oul1-leaf-r08a/b | 8 | 4210024008 | LEAF-32D | 4.32.2F | LCL5NF4NZA | TE8VDD03EU |
| oul1-leaf-r09a/b | 9 | 4210024009 | LEAF-32D | 4.32.2F | NZCLX04V3Z | 2RA5A4MB4X |
| oul1-leaf-r10a/b | 10 | 4210024010 | LEAF-64D | 4.32.2F | DZUY1V1HWG | 14X0SGE5G1 |
| oul1-leaf-r11a/b | 11 | 4210024011 | LEAF-32D | 4.33.1F | T7ZJ3TXVWS | 2A726EG6EX |
| oul1-leaf-r12a/b | 12 | 4210024012 | LEAF-64D | 4.32.2F | 1LVKEFM5CZ | STADU16Y19 |
| oul1-leaf-r13a/b | 13 | 4210024013 | LEAF-32D | 4.33.1F | J2Y2GY56G0 | YDBYVXGY04 |
| oul1-leaf-r14a/b | 14 | 4210024014 | LEAF-64D | 4.32.2F | E4EU3UWHNE | 3T4PHNEERD |
| oul1-leaf-r15a/b | 15 | 4210024015 | LEAF-32D | 4.32.2F | 4A7M3NDTW9 | SV9TWF2F9L |
| oul1-leaf-r16a/b | 16 | 4210024016 | LEAF-32D | 4.33.1F | ZMNST0UE8N | S42CV73KFL |
| oul1-leaf-r17a/b | 17 | 4210024017 | LEAF-32D | 4.32.2F | 3C9PJ9E43U | RDGJEM3119 |
| oul1-leaf-r18a/b | 18 | 4210024018 | LEAF-32D | 4.32.2F | HBZSWM9AEZ | 6MAKCHWE3C |
| oul1-leaf-r19a/b | 19 | 4210024019 | LEAF-64D | 4.33.1F | MFJ9SZ5E00 | LR9T1CAH03 |
| oul1-leaf-r20a/b | 20 | 4210024020 | LEAF-64D | 4.33.1F | 5UUEWPJK4B | 1T5H87X6HX |
| oul1-leaf-r21a/b | 21 | 4210024021 | LEAF-32D | 4.32.2F | RP3B2H9FH2 | TA7LYNYM97 |
| oul1-leaf-r22a/b | 22 | 4210024022 | LEAF-32D | 4.32.2F | R9FT8S0LFN | PG6SNVP0G2 |
| oul1-leaf-r23a/b | 23 | 4210024023 | LEAF-64D | 4.32.2F | YD71BENWWR | AKU9WF5GLC |
| oul1-leaf-r24a/b | 24 | 4210024024 | LEAF-32D | 4.33.1F | 6MA1PN75KM | NVFJSHB9PZ |
| oul1-leaf-r25a/b | 25 | 4210024025 | LEAF-32D | 4.33.1F | 78EUZ41V8U | 68M3TBBXXN |
| oul1-leaf-r26a/b | 26 | 4210024026 | LEAF-64D | 4.32.2F | 0XRPJNMF6Z | KTTE2JP0YN |
| oul1-leaf-r27a/b | 27 | 4210024027 | LEAF-32D | 4.32.2F | 80DFNJ536H | FB8AZM0KDV |
| oul1-leaf-r28a/b | 28 | 4210024028 | LEAF-32D | 4.32.2F | S8GDR757GK | 5MVSBVH54E |
| oul1-leaf-r29a/b | 29 | 4210024029 | LEAF-32D | 4.32.2F | 2NCNHMRX90 | 9GTMPMUS47 |
| oul1-leaf-r30a/b | 30 | 4210024030 | LEAF-32D | 4.33.1F | HD9B9A03KV | DEHPV30MD0 |
| oul1-leaf-r31a/b | 31 | 4210024031 | LEAF-32D | 4.32.2F | RRL68XDTL9 | YA279PNDZR |
| oul1-leaf-r32a/b | 32 | 4210024032 | LEAF-32D | 4.33.1F | 7GDUCGEJEA | 4AEAMF286W |

### C.4. TMP1

| Leaf pair | Rack | ASN | Model | NOS version | Serial a | Serial b |
|---|---|---|---|---|---|---|
| tmp1-leaf-r01a/b | 1 | 4210032001 | LEAF-32D | 4.32.2F | LRNR80SMTF | HX7651GVH2 |
| tmp1-leaf-r02a/b | 2 | 4210032002 | LEAF-32D | 4.32.2F | MP50D4GDJE | XK2XTFUFCS |
| tmp1-leaf-r03a/b | 3 | 4210032003 | LEAF-64D | 4.32.2F | TS1L1BARX6 | 4FFP1F4U1Y |
| tmp1-leaf-r04a/b | 4 | 4210032004 | LEAF-64D | 4.32.2F | 8TDPTF9NM9 | 85TPZRENFH |
| tmp1-leaf-r05a/b | 5 | 4210032005 | LEAF-32D | 4.32.2F | EKEUC12G6G | ZLVXSUU4H8 |
| tmp1-leaf-r06a/b | 6 | 4210032006 | LEAF-64D | 4.32.2F | HJTYBG2L8B | 6XN42KNKV0 |
| tmp1-leaf-r07a/b | 7 | 4210032007 | LEAF-32D | 4.32.2F | 4MN23ELC18 | D9BEGW1YNS |
| tmp1-leaf-r08a/b | 8 | 4210032008 | LEAF-64D | 4.32.2F | RW8DKMHHV8 | KSK9P7EBTU |
| tmp1-leaf-r09a/b | 9 | 4210032009 | LEAF-32D | 4.32.2F | 62CKX7AY2C | 91C7ZKVE5Z |
| tmp1-leaf-r10a/b | 10 | 4210032010 | LEAF-32D | 4.32.2F | GHJEG23NK4 | 528T2TL71F |
| tmp1-leaf-r11a/b | 11 | 4210032011 | LEAF-64D | 4.33.1F | XXPRY0YD31 | D7MPLUHKST |
| tmp1-leaf-r12a/b | 12 | 4210032012 | LEAF-64D | 4.32.2F | 4J2D4T6P1H | 9LJ7BAMAL9 |
| tmp1-leaf-r13a/b | 13 | 4210032013 | LEAF-64D | 4.32.2F | BD4ES20UZR | J0VURHPL2P |
| tmp1-leaf-r14a/b | 14 | 4210032014 | LEAF-64D | 4.32.2F | CNS2L4SSKP | X2LUBKHSE5 |
| tmp1-leaf-r15a/b | 15 | 4210032015 | LEAF-32D | 4.33.1F | CX7G68T6SW | H2ET01XRGA |
| tmp1-leaf-r16a/b | 16 | 4210032016 | LEAF-32D | 4.32.2F | DU68NF6AP5 | YWZ1CLHYHW |
| tmp1-leaf-r17a/b | 17 | 4210032017 | LEAF-32D | 4.32.2F | CPMVXJFV6G | WCP05ZVRG1 |
| tmp1-leaf-r18a/b | 18 | 4210032018 | LEAF-32D | 4.32.2F | 8KLH1FDRT2 | K2Z9PK3NTP |
| tmp1-leaf-r19a/b | 19 | 4210032019 | LEAF-32D | 4.32.2F | HPFN8JBKPS | S9BXV8BMUM |
| tmp1-leaf-r20a/b | 20 | 4210032020 | LEAF-32D | 4.33.1F | KN60FZDR9X | 8KA9449HJK |
| tmp1-leaf-r21a/b | 21 | 4210032021 | LEAF-32D | 4.32.2F | DESNZDLZGX | XYAX3YYM8H |
| tmp1-leaf-r22a/b | 22 | 4210032022 | LEAF-32D | 4.32.2F | A2738P5VWY | J02PGCG8YC |
| tmp1-leaf-r23a/b | 23 | 4210032023 | LEAF-64D | 4.33.1F | FY4DYUD5GF | FH0V1LPNS4 |
| tmp1-leaf-r24a/b | 24 | 4210032024 | LEAF-32D | 4.32.2F | BGWDZK9CXX | 7RVUW7B4KL |

### C.5. ESP1

| Leaf pair | Rack | ASN | Model | NOS version | Serial a | Serial b |
|---|---|---|---|---|---|---|
| esp1-leaf-r01a/b | 1 | 4210040001 | LEAF-32D | 4.32.2F | VSTTFUPAVK | 36XFDPMJ09 |
| esp1-leaf-r02a/b | 2 | 4210040002 | LEAF-32D | 4.32.2F | C4YN970BBA | DJREWB668C |
| esp1-leaf-r03a/b | 3 | 4210040003 | LEAF-32D | 4.32.2F | 55313DXJZ2 | PV8B7KM7S7 |
| esp1-leaf-r04a/b | 4 | 4210040004 | LEAF-32D | 4.32.2F | JSWT56RZ76 | 3PGTTP9WTF |
| esp1-leaf-r05a/b | 5 | 4210040005 | LEAF-32D | 4.32.2F | M7BGT0BHJW | TM0S1PYC1G |
| esp1-leaf-r06a/b | 6 | 4210040006 | LEAF-32D | 4.32.2F | 8G695N333K | Z34494AYE9 |
| esp1-leaf-r07a/b | 7 | 4210040007 | LEAF-32D | 4.33.1F | 7NHGFT9FZX | 3K0HC0DLAS |
| esp1-leaf-r08a/b | 8 | 4210040008 | LEAF-32D | 4.32.2F | FAHEURMN0X | 8DCWP6V1L1 |
| esp1-leaf-r09a/b | 9 | 4210040009 | LEAF-32D | 4.33.1F | ZEGEKHH7DP | 8VKVLPY6RJ |
| esp1-leaf-r10a/b | 10 | 4210040010 | LEAF-64D | 4.32.2F | 6MH46JB1ZA | VVW86SELKN |
| esp1-leaf-r11a/b | 11 | 4210040011 | LEAF-32D | 4.32.2F | U0KTB6Z7ZN | L5M5S2J6P5 |
| esp1-leaf-r12a/b | 12 | 4210040012 | LEAF-32D | 4.32.2F | T25552UPAH | SAD9HYYTDE |
| esp1-leaf-r13a/b | 13 | 4210040013 | LEAF-64D | 4.32.2F | KPPS15JANZ | W0RN4M434C |
| esp1-leaf-r14a/b | 14 | 4210040014 | LEAF-64D | 4.32.2F | T6K8826M2V | YJHR3XZP5S |
| esp1-leaf-r15a/b | 15 | 4210040015 | LEAF-32D | 4.33.1F | 6XKZD5UCH0 | RE234U7HWV |
| esp1-leaf-r16a/b | 16 | 4210040016 | LEAF-64D | 4.33.1F | EGWUGSGBGN | BZB4N4JGCK |
| esp1-leaf-r17a/b | 17 | 4210040017 | LEAF-32D | 4.32.2F | AR67N82SM7 | FR7BUS0RWZ |
| esp1-leaf-r18a/b | 18 | 4210040018 | LEAF-32D | 4.33.1F | V5Y77YC5FN | HNUDT0NUJD |
| esp1-leaf-r19a/b | 19 | 4210040019 | LEAF-32D | 4.32.2F | 9C3E789HRK | 6MEY1BKGPK |
| esp1-leaf-r20a/b | 20 | 4210040020 | LEAF-32D | 4.33.1F | YU5EXNFM9N | M1SS9U48A5 |
| esp1-leaf-r21a/b | 21 | 4210040021 | LEAF-64D | 4.32.2F | CF6NYXMSV1 | W5DMHWPGUH |
| esp1-leaf-r22a/b | 22 | 4210040022 | LEAF-64D | 4.32.2F | S6HT68HS14 | 3LN40GS457 |
| esp1-leaf-r23a/b | 23 | 4210040023 | LEAF-32D | 4.32.2F | TCAMTKC8N8 | GZ826SMZH0 |
| esp1-leaf-r24a/b | 24 | 4210040024 | LEAF-64D | 4.33.1F | L8WXHW8YVA | EEGU8J1LVX |
| esp1-leaf-r25a/b | 25 | 4210040025 | LEAF-64D | 4.32.2F | TBY8MGRAJA | HVHXFJUH63 |
| esp1-leaf-r26a/b | 26 | 4210040026 | LEAF-32D | 4.32.2F | T0CNH605A9 | MR2GUE65HY |
| esp1-leaf-r27a/b | 27 | 4210040027 | LEAF-64D | 4.32.2F | ME5XUMW863 | 0FFEKNXH5X |
| esp1-leaf-r28a/b | 28 | 4210040028 | LEAF-64D | 4.32.2F | D6X913DMTC | JM2FH6MEFD |
| esp1-leaf-r29a/b | 29 | 4210040029 | LEAF-32D | 4.32.2F | ZL8A46MX8C | 7P0CY69L90 |
| esp1-leaf-r30a/b | 30 | 4210040030 | LEAF-32D | 4.33.1F | JDS1F3ZCJA | SC822SDFGJ |
| esp1-leaf-r31a/b | 31 | 4210040031 | LEAF-32D | 4.32.2F | 0JLHV8HKU0 | VRNZSH1149 |
| esp1-leaf-r32a/b | 32 | 4210040032 | LEAF-32D | 4.32.2F | GESZJSV90Z | 7RRN5UK1RU |
| esp1-leaf-r33a/b | 33 | 4210040033 | LEAF-32D | 4.32.2F | UK21WB9FHD | 2NJHGHM5VL |
| esp1-leaf-r34a/b | 34 | 4210040034 | LEAF-32D | 4.32.2F | A3VGPUA60H | 6KLSZUFNVH |
| esp1-leaf-r35a/b | 35 | 4210040035 | LEAF-32D | 4.33.1F | 01H5G2XEPS | GE69DJTVWX |
| esp1-leaf-r36a/b | 36 | 4210040036 | LEAF-64D | 4.33.1F | UUF5TZNV6J | ZXEMNX8BYU |

## Appendix D: Revision history

| Revision | Date | Change |
|---|---|---|
| 1 | 2019-04-02 | First version for HEL1. |
| 2 | 2019-09-17 | Host name rules for switches. Cable colours. |
| 3 | 2020-03-11 | TMP1 added. |
| 4 | 2020-10-05 | BMC configuration section. IPMI over LAN disabled. |
| 5 | 2021-02-22 | OUL1 added. Storage fabric section. |
| 6 | 2021-08-30 | EVPN multihoming instead of MLAG in the data fabric. |
| 7 | 2022-01-19 | HEL2 added. |
| 8 | 2022-06-07 | Security zones. Bastion hosts. |
| 9 | 2023-01-16 | ESP1 added. Provider deviations for ESP1. |
| 10 | 2023-09-04 | PTP for GPU nodes. Alert thresholds. |
| 11 | 2024-03-25 | Editorial changes. Table 5-1. |
| 12 | 2025-02-10 | Out-of-band reservations for rack infrastructure extended (section 6). Storage VLAN range moved; the old range is now for tenant transit VLANs (section 13). |
| 13 | 2025-09-29 | OUL1 storage hall S and the leased ring (section 17). Old TMP1 deviation withdrawn (section 19). |
| 14 | 2026-10-12 | HEL2 hall B (section 19). BMC firmware baseline for quarter 4 of 2026. Editorial changes. |
