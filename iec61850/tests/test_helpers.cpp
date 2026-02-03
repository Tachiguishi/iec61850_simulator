#include "test_helpers.hpp"

/*
{
  "instance_id": "default_instance",
  "model": {
    "name": "SimulatedIED",
    "manufacturer": "IEC61850Simulator",
    "model": "VirtualIED",
    "revision": "1.0",
    "description": "Default simulated IED",
    "logical_devices": {
      "PROT": {
        "name": "PROT",
        "description": "Protection LD",
        "logical_nodes": {
          "LLN0": {
            "name": "LLN0",
            "class": "LLN0",
            "description": "Logical Node Zero",
            "data_objects": {
              "Mod": {
                "name": "Mod",
                "cdc": "ENC",
                "description": "Mode",
                "attributes": {
                  "stVal": {
                    "name": "stVal",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": true,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637417"
                  },
                  "q": {
                    "name": "q",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": false,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637430"
                  },
                  "t": {
                    "name": "t",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": null,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637436"
                  }
                }
              },
              "Beh": {
                "name": "Beh",
                "cdc": "ENS",
                "description": "Behaviour",
                "attributes": {
                  "stVal": {
                    "name": "stVal",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": true,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637443"
                  },
                  "q": {
                    "name": "q",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": false,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637447"
                  }
                }
              }
            },
            "data_sets": {},
            "report_controls": {},
            "gse_controls": {},
            "smv_controls": {},
            "log_controls": {},
            "setting_group_control": null
          },
          "PTOC1": {
            "name": "PTOC1",
            "class": "PTOC",
            "description": "Overcurrent Protection",
            "data_objects": {
              "Mod": {
                "name": "Mod",
                "cdc": "ENC",
                "description": "Mode",
                "attributes": {
                  "stVal": {
                    "name": "stVal",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": true,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637462"
                  }
                }
              },
              "Op": {
                "name": "Op",
                "cdc": "ACT",
                "description": "Operate",
                "attributes": {
                  "general": {
                    "name": "general",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": false,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637468"
                  },
                  "phsA": {
                    "name": "phsA",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": false,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637471"
                  },
                  "phsB": {
                    "name": "phsB",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": false,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637474"
                  },
                  "phsC": {
                    "name": "phsC",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": false,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637477"
                  },
                  "q": {
                    "name": "q",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": false,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637480"
                  },
                  "t": {
                    "name": "t",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": null,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637483"
                  }
                }
              }
            },
            "data_sets": {},
            "report_controls": {},
            "gse_controls": {},
            "smv_controls": {},
            "log_controls": {},
            "setting_group_control": null
          },
          "XCBR1": {
            "name": "XCBR1",
            "class": "XCBR",
            "description": "Circuit Breaker",
            "data_objects": {
              "Pos": {
                "name": "Pos",
                "cdc": "DPC",
                "description": "Position",
                "attributes": {
                  "stVal": {
                    "name": "stVal",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": true,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637493"
                  },
                  "q": {
                    "name": "q",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": false,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637498"
                  },
                  "t": {
                    "name": "t",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": null,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637501"
                  },
                  "ctlModel": {
                    "name": "ctlModel",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": true,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637505"
                  }
                }
              }
            },
            "data_sets": {},
            "report_controls": {},
            "gse_controls": {},
            "smv_controls": {},
            "log_controls": {},
            "setting_group_control": null
          }
        }
      },
      "MEAS": {
        "name": "MEAS",
        "description": "Measurement LD",
        "logical_nodes": {
          "MMXU1": {
            "name": "MMXU1",
            "class": "MMXU",
            "description": "Measurement Unit",
            "data_objects": {
              "TotW": {
                "name": "TotW",
                "cdc": "MV",
                "description": "Total Active Power",
                "attributes": {
                  "mag": {
                    "name": "mag",
                    "type": "BOOLEAN",
                    "fc": "MX",
                    "attributes": {
                      "f": {
                        "name": "f",
                        "type": "BOOLEAN",
                        "fc": "ST",
                        "value": true,
                        "quality": 0,
                        "timestamp": "2026-01-31T16:51:25.637524"
                      }
                    }
                  },
                  "q": {
                    "name": "q",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": false,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637529"
                  },
                  "t": {
                    "name": "t",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": null,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637532"
                  }
                }
              },
              "Hz": {
                "name": "Hz",
                "cdc": "MV",
                "description": "Frequency",
                "attributes": {
                  "mag": {
                    "name": "mag",
                    "type": "BOOLEAN",
                    "fc": "MX",
                    "attributes": {
                      "f": {
                        "name": "f",
                        "type": "BOOLEAN",
                        "fc": "ST",
                        "value": true,
                        "quality": 0,
                        "timestamp": "2026-01-31T16:51:25.637540"
                      }
                    }
                  },
                  "q": {
                    "name": "q",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": false,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637544"
                  },
                  "t": {
                    "name": "t",
                    "type": "BOOLEAN",
                    "fc": "ST",
                    "value": null,
                    "quality": 0,
                    "timestamp": "2026-01-31T16:51:25.637546"
                  }
                }
              }
            },
            "data_sets": {},
            "report_controls": {},
            "gse_controls": {},
            "smv_controls": {},
            "log_controls": {},
            "setting_group_control": null
          }
        }
      }
    }
  }
}
*/
void pack_default_model_payload(msgpack::packer<msgpack::sbuffer>& pk) {
  pk.pack_map(2);
  pk.pack("instance_id");
  pk.pack("default_instance");
  pk.pack("model");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("SimulatedIED");
    pk.pack("manufacturer");
    pk.pack("IEC61850Simulator");
    pk.pack("model");
    pk.pack("VirtualIED");
    pk.pack("revision");
    pk.pack("1.0");
    pk.pack("description");
    pk.pack("Default simulated IED");
    pk.pack("logical_devices");
      pk.pack_map(2);
      pk.pack("PROT");
        pk.pack_map(3);
        pk.pack("name");
        pk.pack("PROT");
        pk.pack("description");
        pk.pack("Protection LD");
        pk.pack("logical_nodes");
          pk.pack_map(3);
          pk.pack("LLN0");
            pk.pack_map(10);
            pk.pack("name");
            pk.pack("LLN0");
            pk.pack("class");
            pk.pack("LLN0");
            pk.pack("description");
            pk.pack("Logical Node Zero");
            pk.pack("data_objects");
              pk.pack_map(2);
              pk.pack("Mod");
                pk.pack_map(4);
                pk.pack("name");
                pk.pack("Mod");
                pk.pack("cdc");
                pk.pack("ENC");
                pk.pack("description");
                pk.pack("Mode");
                pk.pack("attributes");
                  pk.pack_map(3);
    pk.pack("stVal");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("stVal");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(true);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637417");
    pk.pack("q");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("q");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(false);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637430");
    pk.pack("t");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("t");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack_nil();
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637436");

    pk.pack("Beh");
    pk.pack_map(4);
    pk.pack("name");
    pk.pack("Beh");
    pk.pack("cdc");
    pk.pack("ENS");
    pk.pack("description");
    pk.pack("Behaviour");
    pk.pack("attributes");
    pk.pack_map(2);
    pk.pack("stVal");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("stVal");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(true);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637443");
    pk.pack("q");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("q");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(false);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637447");

    pk.pack("data_sets");
    pk.pack_map(0);
    pk.pack("report_controls");
    pk.pack_map(0);
    pk.pack("gse_controls");
    pk.pack_map(0);
    pk.pack("smv_controls");
    pk.pack_map(0);
    pk.pack("log_controls");
    pk.pack_map(0);
    pk.pack("setting_group_control");
    pk.pack_nil();

    pk.pack("PTOC1");
    pk.pack_map(10);
    pk.pack("name");
    pk.pack("PTOC1");
    pk.pack("class");
    pk.pack("PTOC");
    pk.pack("description");
    pk.pack("Overcurrent Protection");
    pk.pack("data_objects");
    pk.pack_map(2);

    pk.pack("Mod");
    pk.pack_map(4);
    pk.pack("name");
    pk.pack("Mod");
    pk.pack("cdc");
    pk.pack("ENC");
    pk.pack("description");
    pk.pack("Mode");
    pk.pack("attributes");
    pk.pack_map(1);
    pk.pack("stVal");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("stVal");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(true);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637462");

    pk.pack("Op");
    pk.pack_map(4);
    pk.pack("name");
    pk.pack("Op");
    pk.pack("cdc");
    pk.pack("ACT");
    pk.pack("description");
    pk.pack("Operate");
    pk.pack("attributes");
    pk.pack_map(6);
    pk.pack("general");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("general");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(false);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637468");
    pk.pack("phsA");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("phsA");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(false);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637471");
    pk.pack("phsB");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("phsB");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(false);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637474");
    pk.pack("phsC");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("phsC");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(false);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637477");
    pk.pack("q");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("q");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(false);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637480");
    pk.pack("t");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("t");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack_nil();
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637483");

    pk.pack("data_sets");
    pk.pack_map(0);
    pk.pack("report_controls");
    pk.pack_map(0);
    pk.pack("gse_controls");
    pk.pack_map(0);
    pk.pack("smv_controls");
    pk.pack_map(0);
    pk.pack("log_controls");
    pk.pack_map(0);
    pk.pack("setting_group_control");
    pk.pack_nil();

    pk.pack("XCBR1");
    pk.pack_map(10);
    pk.pack("name");
    pk.pack("XCBR1");
    pk.pack("class");
    pk.pack("XCBR");
    pk.pack("description");
    pk.pack("Circuit Breaker");
    pk.pack("data_objects");
    pk.pack_map(1);

    pk.pack("Pos");
    pk.pack_map(4);
    pk.pack("name");
    pk.pack("Pos");
    pk.pack("cdc");
    pk.pack("DPC");
    pk.pack("description");
    pk.pack("Position");
    pk.pack("attributes");
    pk.pack_map(4);
    pk.pack("stVal");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("stVal");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(true);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637493");
    pk.pack("q");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("q");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(false);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637498");
    pk.pack("t");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("t");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack_nil();
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637501");
    pk.pack("ctlModel");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("ctlModel");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(true);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637505");

    pk.pack("data_sets");
    pk.pack_map(0);
    pk.pack("report_controls");
    pk.pack_map(0);
    pk.pack("gse_controls");
    pk.pack_map(0);
    pk.pack("smv_controls");
    pk.pack_map(0);
    pk.pack("log_controls");
    pk.pack_map(0);
    pk.pack("setting_group_control");
    pk.pack_nil();

    pk.pack("MEAS");
    pk.pack_map(3);
    pk.pack("name");
    pk.pack("MEAS");
    pk.pack("description");
    pk.pack("Measurement LD");
    pk.pack("logical_nodes");
    pk.pack_map(1);

    pk.pack("MMXU1");
    pk.pack_map(10);
    pk.pack("name");
    pk.pack("MMXU1");
    pk.pack("class");
    pk.pack("MMXU");
    pk.pack("description");
    pk.pack("Measurement Unit");
    pk.pack("data_objects");
    pk.pack_map(2);

    pk.pack("TotW");
    pk.pack_map(4);
    pk.pack("name");
    pk.pack("TotW");
    pk.pack("cdc");
    pk.pack("MV");
    pk.pack("description");
    pk.pack("Total Active Power");
    pk.pack("attributes");
    pk.pack_map(3);
    pk.pack("mag");
    pk.pack_map(4);
    pk.pack("name");
    pk.pack("mag");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("MX");
    pk.pack("attributes");
    pk.pack_map(1);
    pk.pack("f");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("f");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(true);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637524");
    pk.pack("q");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("q");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(false);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637529");
    pk.pack("t");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("t");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack_nil();
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637532");

    pk.pack("Hz");
    pk.pack_map(4);
    pk.pack("name");
    pk.pack("Hz");
    pk.pack("cdc");
    pk.pack("MV");
    pk.pack("description");
    pk.pack("Frequency");
    pk.pack("attributes");
    pk.pack_map(3);
    pk.pack("mag");
    pk.pack_map(4);
    pk.pack("name");
    pk.pack("mag");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("MX");
    pk.pack("attributes");
    pk.pack_map(1);
    pk.pack("f");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("f");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(true);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637540");
    pk.pack("q");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("q");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack(false);
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637544");
    pk.pack("t");
    pk.pack_map(6);
    pk.pack("name");
    pk.pack("t");
    pk.pack("type");
    pk.pack("BOOLEAN");
    pk.pack("fc");
    pk.pack("ST");
    pk.pack("value");
    pk.pack_nil();
    pk.pack("quality");
    pk.pack(0);
    pk.pack("timestamp");
    pk.pack("2026-01-31T16:51:25.637546");

    pk.pack("data_sets");
    pk.pack_map(0);
    pk.pack("report_controls");
    pk.pack_map(0);
    pk.pack("gse_controls");
    pk.pack_map(0);
    pk.pack("smv_controls");
    pk.pack_map(0);
    pk.pack("log_controls");
    pk.pack_map(0);
    pk.pack("setting_group_control");
    pk.pack_nil();
}
