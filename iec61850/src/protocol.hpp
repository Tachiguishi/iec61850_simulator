#pragma once

#include <optional>
#include <string>
#include <unordered_map>
#include <variant>
#include <vector>

namespace ipc {

struct ErrorPayload {
    std::string message;
};

struct Request {
    std::string id;
    std::string type;   // "request"
    std::string action; // e.g. "server.start"
    std::unordered_map<std::string, std::variant<std::string, int64_t, double, bool>> payload;
};

struct Response {
    std::string id;
    std::string type;   // "response"
    std::unordered_map<std::string, std::string> payload; // placeholder
    std::optional<ErrorPayload> error;
};

} // namespace ipc
