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

nlohmann::json execute_action_json(const std::string& action,
                                  BackendContext& context,
                                  const nlohmann::json& payload) {
  ipc::codec::Request request;
  request.id = "test-id";
  request.action = action;
  request.payload = payload;
  std::string response_bytes = ipc::actions::handle_action(request, context);
  return unpack_msgpack_bytes_to_json(response_bytes);
}

nlohmann::json load_model_payload_from_file(const std::string& model_path, bool modelOnly) {
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
  nlohmann::json result;
  result["instance_id"] = "default_instance";
  result["model"] = payload;
   if(modelOnly){
    result["modelOnly"] = true;
  }
  return result;
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
