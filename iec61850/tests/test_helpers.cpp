#include "test_helpers.hpp"

#include "action/action.hpp"
#include "msgpack_codec.hpp"

#include <cctype>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits.h>
#include <stdexcept>
#include <unistd.h>

msgpack::object_handle pack_msgpack_object(const std::function<void(msgpack::packer<msgpack::sbuffer>&)>& pack_fn) {
  msgpack::sbuffer buffer;
  msgpack::packer<msgpack::sbuffer> pk(&buffer);
  pack_fn(pk);
  return msgpack::unpack(buffer.data(), buffer.size());
}

void pack_json_value(msgpack::packer<msgpack::sbuffer>& pk, const nlohmann::json& value) {
  const auto pack_json = [&pk](const nlohmann::json& current, const auto& self) -> void {
    if (current.is_null()) {
      pk.pack_nil();
      return;
    }
    if (current.is_boolean()) {
      pk.pack(current.get<bool>());
      return;
    }
    if (current.is_number_integer()) {
      pk.pack(current.get<int64_t>());
      return;
    }
    if (current.is_number_unsigned()) {
      pk.pack(current.get<uint64_t>());
      return;
    }
    if (current.is_number_float()) {
      pk.pack(current.get<double>());
      return;
    }
    if (current.is_string()) {
      pk.pack(current.get<std::string>());
      return;
    }
    if (current.is_array()) {
      pk.pack_array(current.size());
      for (const auto& item : current) {
        self(item, self);
      }
      return;
    }
    if (current.is_object()) {
      pk.pack_map(current.size());
      for (auto it = current.begin(); it != current.end(); ++it) {
        pk.pack(it.key());
        self(it.value(), self);
      }
      return;
    }

    throw std::runtime_error("Unsupported JSON value while packing msgpack");
  };

  pack_json(value, pack_json);
}

msgpack::object_handle make_payload_from_json(const nlohmann::json& value) {
  return pack_msgpack_object([&value](msgpack::packer<msgpack::sbuffer>& pk) {
    pack_json_value(pk, value);
  });
}

nlohmann::json unpack_msgpack_bytes_to_json(const std::string& bytes) {
  try {
    std::vector<std::uint8_t> raw(bytes.begin(), bytes.end());
    return nlohmann::json::from_msgpack(raw);
  } catch (const std::exception& ex) {
    std::cerr << "msgpack decode failed: " << ex.what() << std::endl;
    std::cerr << "bytes.size() = " << bytes.size() << std::endl;
    std::cerr << "bytes (hex): ";
    for (unsigned char c : bytes) {
      std::cerr << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(c) << " ";
    }
    std::cerr << std::dec << std::endl;

    std::cerr << "bytes (ascii): ";
    for (unsigned char c : bytes) {
      if (std::isprint(c)) {
        std::cerr << c;
      } else {
        std::cerr << ".";
      }
    }
    std::cerr << std::endl;
    throw;
  }
}

nlohmann::json execute_action_json(const std::string& action, BackendContext& context) {
  msgpack::object dummy;
  return execute_action_json(action, context, dummy, false);
}

nlohmann::json execute_action_json(const std::string& action,
                                  BackendContext& context,
                                  const msgpack::object& payload,
                                  bool has_payload) {
  msgpack::sbuffer request_buffer;
  msgpack::packer<msgpack::sbuffer> pk(&request_buffer);

  pk.pack_map(has_payload ? 3 : 2);
  pk.pack("id");
  pk.pack("test-id");
  pk.pack("method");
  pk.pack(action);
  if (has_payload) {
    pk.pack("params");
    pk.pack(payload);
  }

  std::string request_bytes(request_buffer.data(), request_buffer.size());
  std::string response_bytes = ipc::actions::handle_action(request_bytes, context);
  return unpack_msgpack_bytes_to_json(response_bytes);
}

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

void pack_payload_from_json_file(msgpack::packer<msgpack::sbuffer>& pk, const std::string& model_path){
  // 如果路径是相对路径，则是相对当前执行文件的路径
  char buffer[PATH_MAX] = {0};
  ssize_t len = ::readlink("/proc/self/exe", buffer, sizeof(buffer) - 1);
  std::filesystem::path json_path = model_path;
  if (len > 0) {
    buffer[len] = '\0';
    std::filesystem::path exe_path(buffer);
    json_path = exe_path.parent_path() / model_path;
  }
  std::ifstream input(json_path);
  if (!input.is_open()) {
    throw std::runtime_error("Failed to open JSON file: " + model_path);
  }

  nlohmann::json payload;
  input >> payload;

  nlohmann::json response_json;
  response_json["instance_id"] = "default_instance";
  response_json["model"] = payload;

  pack_json_value(pk, response_json);
}
