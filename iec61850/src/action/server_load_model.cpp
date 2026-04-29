#include "action_handle.hpp"

#include "../logger.hpp"
#include "../msgpack_codec.hpp"

#include <log4cplus/loggingmacros.h>

#include <algorithm>
#include <cctype>
#include <climits>
#include <cstdlib>
#include <functional>
#include <unordered_map>

namespace ipc::actions {

namespace {

FunctionalConstraint map_fc(const std::string& fc) {
    std::string fc_upper = fc;
    std::transform(fc_upper.begin(), fc_upper.end(), fc_upper.begin(),
                   [](unsigned char ch) { return static_cast<char>(std::toupper(ch)); });
    if (fc_upper == "ST") return IEC61850_FC_ST;
    if (fc_upper == "MX") return IEC61850_FC_MX;
    if (fc_upper == "SP") return IEC61850_FC_SP;
    if (fc_upper == "SV") return IEC61850_FC_SV;
    if (fc_upper == "CF") return IEC61850_FC_CF;
    if (fc_upper == "DC") return IEC61850_FC_DC;
    if (fc_upper == "SG") return IEC61850_FC_SG;
    if (fc_upper == "SE") return IEC61850_FC_SE;
    if (fc_upper == "SR") return IEC61850_FC_SR;
    if (fc_upper == "OR") return IEC61850_FC_OR;
    if (fc_upper == "BL") return IEC61850_FC_BL;
    if (fc_upper == "EX") return IEC61850_FC_EX;
    if (fc_upper == "CO") return IEC61850_FC_CO;
    return IEC61850_FC_ST;
}

DataAttributeType map_type(const std::string& type) {
    std::string type_upper = type;
    std::transform(type_upper.begin(), type_upper.end(), type_upper.begin(),
                   [](unsigned char ch) { return static_cast<char>(std::toupper(ch)); });
    if (type_upper == "BOOLEAN" || type_upper == "BOOL") return IEC61850_BOOLEAN;
    if (type_upper == "INT8") return IEC61850_INT8;
    if (type_upper == "INT16") return IEC61850_INT16;
    if (type_upper == "INT32") return IEC61850_INT32;
    if (type_upper == "INT64") return IEC61850_INT64;
    if (type_upper == "INT8U") return IEC61850_INT8U;
    if (type_upper == "INT16U") return IEC61850_INT16U;
    if (type_upper == "INT24U") return IEC61850_INT24U;
    if (type_upper == "INT32U") return IEC61850_INT32U;
    if (type_upper == "FLOAT32") return IEC61850_FLOAT32;
    if (type_upper == "FLOAT64") return IEC61850_FLOAT64;
    if (type_upper == "ENUM" || type_upper == "ENUMERATED") return IEC61850_ENUMERATED;
    if (type_upper == "VISSTRING32" || type_upper == "VIS_STRING_32") return IEC61850_VISIBLE_STRING_32;
    if (type_upper == "VISSTRING64" || type_upper == "VIS_STRING_64") return IEC61850_VISIBLE_STRING_64;
    if (type_upper == "VISSTRING129" || type_upper == "VIS_STRING_129") return IEC61850_VISIBLE_STRING_129;
    if (type_upper == "VISSTRING255" || type_upper == "VIS_STRING_255") return IEC61850_VISIBLE_STRING_255;
    if (type_upper == "UNICODESTRING255" || type_upper == "UNICODE_STRING_255") return IEC61850_UNICODE_STRING_255;
    if (type_upper == "OCTETSTRING64" || type_upper == "OCTET_STRING_64") return IEC61850_OCTET_STRING_64;
    if (type_upper == "QUALITY") return IEC61850_QUALITY;
    if (type_upper == "TIMESTAMP") return IEC61850_TIMESTAMP;
    if (type_upper == "CHECK") return IEC61850_CHECK;
    if (type_upper == "STRUCT" || type_upper == "STRUCTURE") return IEC61850_CONSTRUCTED;
    return IEC61850_VISIBLE_STRING_255;
}

bool object_truthy(const nlohmann::json& obj) {
    if (obj.is_boolean()) {
        return obj.get<bool>();
    }
    if (obj.is_number_integer() || obj.is_number_unsigned()) {
        return ipc::codec::as_int64(obj, 0) != 0;
    }
    if (obj.is_string()) {
        std::string value = obj.get<std::string>();
        std::transform(value.begin(), value.end(), value.begin(),
                       [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
        return value == "true" || value == "1" || value == "yes" || value == "on";
    }
    return false;
}

int32_t parse_int32_fallback(const nlohmann::json& obj, int32_t fallback = 0) {
    if (obj.is_number_integer() || obj.is_number_unsigned()) {
        return static_cast<int32_t>(ipc::codec::as_int64(obj, fallback));
    }
    if (obj.is_string()) {
        std::string value = obj.get<std::string>();
        char* end = nullptr;
        long parsed = std::strtol(value.c_str(), &end, 10);
        if (end && *end == '\0') {
            return static_cast<int32_t>(parsed);
        }
    }
    return fallback;
}

int map_ctl_model_string(const std::string& value) {
    std::string lower = value;
    std::transform(lower.begin(), lower.end(), lower.begin(),
                   [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
    if (lower == "status-only") return 0;
    if (lower == "direct-with-normal-security") return 1;
    if (lower == "sbo-with-normal-security") return 2;
    if (lower == "direct-with-enhanced-security") return 3;
    if (lower == "sbo-with-enhanced-security") return 4;
    return -1;
}

bool parse_hex_bytes(const std::string& input, uint8_t* out, size_t out_len) {
    std::string hex;
    hex.reserve(input.size());
    for (char ch : input) {
        if (std::isxdigit(static_cast<unsigned char>(ch))) {
            hex.push_back(ch);
        }
    }
    if (hex.size() != out_len * 2) {
        return false;
    }
    for (size_t i = 0; i < out_len; ++i) {
        std::string byte_str = hex.substr(i * 2, 2);
        char* end = nullptr;
        unsigned long value = std::strtoul(byte_str.c_str(), &end, 16);
        if (!end || *end != '\0') {
            return false;
        }
        out[i] = static_cast<uint8_t>(value & 0xFFu);
    }
    return true;
}

uint32_t parse_uint32_hex_default(const nlohmann::json& obj) {
    if (obj.is_number_integer() || obj.is_number_unsigned()) {
        return static_cast<uint32_t>(ipc::codec::as_int64(obj, 0));
    }
    if (obj.is_string()) {
        std::string value = obj.get<std::string>();
        char* end = nullptr;
        unsigned long parsed = std::strtoul(value.c_str(), &end, 16);
        if (end && *end == '\0') {
            return static_cast<uint32_t>(parsed);
        }
    }
    return 0;
}

uint32_t parse_uint32_auto_base(const nlohmann::json& obj) {
    if (obj.is_number_integer() || obj.is_number_unsigned()) {
        return static_cast<uint32_t>(ipc::codec::as_int64(obj, 0));
    }
    if (obj.is_string()) {
        std::string value = obj.get<std::string>();
        int base = 10;
        if (value.rfind("0x", 0) == 0 || value.rfind("0X", 0) == 0) {
            base = 16;
        } else {
            for (char ch : value) {
                if (std::isalpha(static_cast<unsigned char>(ch))) {
                    base = 16;
                    break;
                }
            }
        }
        char* end = nullptr;
        unsigned long parsed = std::strtoul(value.c_str(), &end, base);
        if (end && *end == '\0') {
            return static_cast<uint32_t>(parsed);
        }
    }
    return 0;
}

bool is_named_collection(const nlohmann::json* obj) {
    return obj && (obj->is_object() || obj->is_array());
}

std::string extract_name_or_fallback(const nlohmann::json& item, const std::string& fallback = "") {
    if (auto name_obj = ipc::codec::find_key(item, "name")) {
        std::string name = ipc::codec::as_string(*name_obj, fallback);
        if (!name.empty()) {
            return name;
        }
    }
    return fallback;
}

void for_each_named_item(const nlohmann::json* collection,
                         const std::function<void(const std::string&, const nlohmann::json&)>& callback) {
    if (!collection) {
        return;
    }

    if (collection->is_object()) {
        for (auto it = collection->begin(); it != collection->end(); ++it) {
            callback(it.key(), it.value());
        }
        return;
    }

    if (!collection->is_array()) {
        return;
    }

    for (const auto& item : *collection) {
        if (!item.is_object()) {
            continue;
        }
        const std::string name = extract_name_or_fallback(item);
        if (name.empty()) {
            continue;
        }
        callback(name, item);
    }
}

MmsValue* create_value_from_msg(const nlohmann::json& obj, DataAttributeType type) {
    if (obj.is_null()) {
        return nullptr;
    }

    switch (type) {
        case IEC61850_BOOLEAN:
            return MmsValue_newBoolean(object_truthy(obj));
        case IEC61850_INT8:
        case IEC61850_INT16:
        case IEC61850_INT32:
            return MmsValue_newIntegerFromInt32(parse_int32_fallback(obj));
        case IEC61850_ENUMERATED: {
            if (obj.is_string()) {
                int mapped = map_ctl_model_string(obj.get<std::string>());
                if (mapped >= 0) {
                    return MmsValue_newIntegerFromInt32(mapped);
                }
            }
            int32_t parsed = parse_int32_fallback(obj, INT32_MIN);
            if (parsed == INT32_MIN) {
                return nullptr;
            }
            return MmsValue_newIntegerFromInt32(parsed);
        }
        case IEC61850_INT64:
            return MmsValue_newIntegerFromInt64(static_cast<int64_t>(ipc::codec::as_int64(obj)));
        case IEC61850_INT8U:
        case IEC61850_INT16U:
        case IEC61850_INT24U:
        case IEC61850_INT32U:
            return MmsValue_newUnsignedFromUint32(static_cast<uint32_t>(ipc::codec::as_int64(obj)));
        case IEC61850_FLOAT32:
            return MmsValue_newFloat(static_cast<float>(ipc::codec::as_double(obj)));
        case IEC61850_FLOAT64:
            return MmsValue_newDouble(ipc::codec::as_double(obj));
        case IEC61850_VISIBLE_STRING_32:
        case IEC61850_VISIBLE_STRING_64:
        case IEC61850_VISIBLE_STRING_129:
        case IEC61850_VISIBLE_STRING_255:
        case IEC61850_UNICODE_STRING_255: {
            std::string value = ipc::codec::as_string(obj, "");
            if (type == IEC61850_UNICODE_STRING_255) {
                return MmsValue_newMmsString(value.c_str());
            }
            return MmsValue_newVisibleString(value.c_str());
        }
        default:
            return nullptr;
    }
}

void create_data_object_recursive(const std::string& name, ModelNode* parent, const nlohmann::json& do_obj);

void create_attribute_recursive(const std::string& name, ModelNode* parent, const nlohmann::json& attr_obj) {
    std::string type_str;
    std::string fc_str = "ST";

    if (auto type_obj = ipc::codec::find_key(attr_obj, "type")) {
        type_str = ipc::codec::as_string(*type_obj);
    }
    if (auto fc_obj = ipc::codec::find_key(attr_obj, "fc")) {
        fc_str = ipc::codec::as_string(*fc_obj);
    }

    auto attributes_obj = ipc::codec::find_key(attr_obj, "attributes");
    bool has_children = is_named_collection(attributes_obj);

    DataAttributeType attr_type = has_children ? IEC61850_CONSTRUCTED : map_type(type_str);
    FunctionalConstraint fc = map_fc(fc_str);
    DataAttribute* da = DataAttribute_create(name.c_str(), parent, attr_type, fc, 0, 0, 0);

    if (has_children) {
        for_each_named_item(attributes_obj, [da](const std::string& child_name, const nlohmann::json& child_attr) {
            create_attribute_recursive(child_name, reinterpret_cast<ModelNode*>(da), child_attr);
        });
        return;
    }

    if (auto value_obj = ipc::codec::find_key(attr_obj, "value")) {
        MmsValue* value = create_value_from_msg(*value_obj, attr_type);
        if (value) {
            DataAttribute_setValue(da, value);
        }
    }
}

void create_data_object_recursive(const std::string& name, ModelNode* parent, const nlohmann::json& do_obj) {
    DataObject* dobj = DataObject_create(name.c_str(), parent, 0);

    auto attrs_obj = ipc::codec::find_key(do_obj, "attributes");
    if (!is_named_collection(attrs_obj)) {
        return;
    }

    for_each_named_item(attrs_obj, [dobj](const std::string& attr_name, const nlohmann::json& attr_value) {
        if (ipc::codec::find_key(attr_value, "cdc")) {
            create_data_object_recursive(attr_name, reinterpret_cast<ModelNode*>(dobj), attr_value);
        } else {
            create_attribute_recursive(attr_name, reinterpret_cast<ModelNode*>(dobj), attr_value);
        }
    });
}

IedModel* build_model_from_json(const nlohmann::json& model_obj, std::string& out_ied_name) {
    std::string ied_name = "IED";
    if (auto name_obj = ipc::codec::find_key(model_obj, "name")) {
        ied_name = ipc::codec::as_string(*name_obj, "IED");
    }
    out_ied_name = ied_name;

    IedModel* model = IedModel_create(ied_name.c_str());
    IedModel_setIedNameForDynamicModel(model, ied_name.c_str());

    std::unordered_map<std::string, GSEControlBlock*> gse_controls;
    std::unordered_map<std::string, SVControlBlock*> smv_controls;
    std::unordered_map<std::string, Log*> log_instances;

    auto lds_obj = ipc::codec::find_key(model_obj, "logical_devices");
    if (!is_named_collection(lds_obj)) {
        return model;
    }

    for_each_named_item(lds_obj, [&](const std::string& ld_name, const nlohmann::json& ld_obj) {
        if (!ld_obj.is_object() || ld_name.empty()) {
            return;
        }

        LogicalDevice* ld = LogicalDevice_create(ld_name.c_str(), model);

        auto ln_obj = ipc::codec::find_key(ld_obj, "logical_nodes");
        if (!is_named_collection(ln_obj)) {
            return;
        }

        for_each_named_item(ln_obj, [&](const std::string& ln_name, const nlohmann::json& ln_value) {
            if (!ln_value.is_object() || ln_name.empty()) {
                return;
            }

            LogicalNode* ln = LogicalNode_create(ln_name.c_str(), ld);

            auto do_obj = ipc::codec::find_key(ln_value, "data_objects");
            if (is_named_collection(do_obj)) {
                for_each_named_item(do_obj, [ln](const std::string& do_name, const nlohmann::json& do_value) {
                    create_data_object_recursive(do_name, reinterpret_cast<ModelNode*>(ln), do_value);
                });
            }

            auto data_sets_obj = ipc::codec::find_key(ln_value, "data_sets");
            if (is_named_collection(data_sets_obj)) {
                for_each_named_item(data_sets_obj, [ln](const std::string& raw_ds_name, const nlohmann::json& ds_value) {
                    std::string ds_name = extract_name_or_fallback(ds_value, raw_ds_name);
                    if (ds_name.empty()) {
                        return;
                    }

                    DataSet* data_set = DataSet_create(ds_name.c_str(), ln);
                    auto fcdas_obj = ipc::codec::find_key(ds_value, "fcdas");
                    if (fcdas_obj && fcdas_obj->is_array()) {
                        for (const auto& fcda : *fcdas_obj) {
                            std::string ref = ipc::codec::as_string(fcda, "");
                            if (!ref.empty()) {
                                DataSetEntry_create(data_set, ref.c_str(), -1, nullptr);
                            }
                        }
                    }
                });
            }

            auto report_controls_obj = ipc::codec::find_key(ln_value, "report_controls");
            if (is_named_collection(report_controls_obj)) {
                for_each_named_item(report_controls_obj, [ln](const std::string& raw_rc_name, const nlohmann::json& rc_val) {
                    std::string rc_name = extract_name_or_fallback(rc_val, raw_rc_name);
                    if (rc_name.empty()) {
                        return;
                    }

                    bool buffered = false;
                    if (auto buffered_obj = ipc::codec::find_key(rc_val, "buffered")) {
                        buffered = object_truthy(*buffered_obj);
                    }

                    std::string dataset;
                    if (auto dataset_obj = ipc::codec::find_key(rc_val, "dataset")) {
                        dataset = ipc::codec::as_string(*dataset_obj, "");
                    }

                    std::string rpt_id;
                    if (auto rptid_obj = ipc::codec::find_key(rc_val, "rptid")) {
                        rpt_id = ipc::codec::as_string(*rptid_obj, "");
                    }

                    uint32_t conf_rev = 1;
                    if (auto conf_obj = ipc::codec::find_key(rc_val, "conf_rev")) {
                        conf_rev = static_cast<uint32_t>(ipc::codec::as_int64(*conf_obj, 1));
                    } else if (auto conf_obj = ipc::codec::find_key(rc_val, "confRev")) {
                        conf_rev = static_cast<uint32_t>(ipc::codec::as_int64(*conf_obj, 1));
                    }

                    uint32_t buf_tm = 0;
                    if (auto buf_tm_obj = ipc::codec::find_key(rc_val, "buf_time")) {
                        buf_tm = static_cast<uint32_t>(ipc::codec::as_int64(*buf_tm_obj, 0));
                    }

                    uint32_t intg_pd = 0;
                    if (auto intg_obj = ipc::codec::find_key(rc_val, "intg_pd")) {
                        intg_pd = static_cast<uint32_t>(ipc::codec::as_int64(*intg_obj, 0));
                    }

                    uint8_t trg_ops = 0;
                    uint8_t opt_flds = 0;
                    auto options_obj = ipc::codec::find_key(rc_val, "options");
                    if (options_obj && options_obj->is_object()) {
                        if (auto opt = ipc::codec::find_key(*options_obj, "dataChange"); opt && object_truthy(*opt)) trg_ops |= TRG_OPT_DATA_CHANGED;
                        if (auto opt = ipc::codec::find_key(*options_obj, "qualityChange"); opt && object_truthy(*opt)) trg_ops |= TRG_OPT_QUALITY_CHANGED;
                        if (auto opt = ipc::codec::find_key(*options_obj, "dataUpdate"); opt && object_truthy(*opt)) trg_ops |= TRG_OPT_DATA_UPDATE;
                        if (auto opt = ipc::codec::find_key(*options_obj, "integrityCheck"); opt && object_truthy(*opt)) trg_ops |= TRG_OPT_INTEGRITY;
                        if (auto opt = ipc::codec::find_key(*options_obj, "seqNum"); opt && object_truthy(*opt)) opt_flds |= RPT_OPT_SEQ_NUM;
                        if (auto opt = ipc::codec::find_key(*options_obj, "timeStamp"); opt && object_truthy(*opt)) opt_flds |= RPT_OPT_TIME_STAMP;
                        if (auto opt = ipc::codec::find_key(*options_obj, "dataSet"); opt && object_truthy(*opt)) opt_flds |= RPT_OPT_DATA_SET;
                        if (auto opt = ipc::codec::find_key(*options_obj, "reasonForInclusion"); opt && object_truthy(*opt)) opt_flds |= RPT_OPT_REASON_FOR_INCLUSION;
                        if (auto opt = ipc::codec::find_key(*options_obj, "configRevision"); opt && object_truthy(*opt)) opt_flds |= RPT_OPT_CONF_REV;
                        if (auto opt = ipc::codec::find_key(*options_obj, "bufferOverflow"); opt && object_truthy(*opt)) opt_flds |= RPT_OPT_BUFFER_OVERFLOW;
                        if (auto opt = ipc::codec::find_key(*options_obj, "dataReference"); opt && object_truthy(*opt)) opt_flds |= RPT_OPT_DATA_REFERENCE;
                        if (auto opt = ipc::codec::find_key(*options_obj, "entryId"); opt && object_truthy(*opt)) opt_flds |= RPT_OPT_ENTRY_ID;
                    }

                    const char* rpt_id_ptr = rpt_id.empty() ? nullptr : rpt_id.c_str();
                    const char* dataset_ptr = dataset.empty() ? nullptr : dataset.c_str();
                    ReportControlBlock_create(rc_name.c_str(), ln, rpt_id_ptr, buffered, dataset_ptr,
                                              conf_rev, trg_ops, opt_flds, buf_tm, intg_pd);
                });
            }

            auto gse_controls_obj = ipc::codec::find_key(ln_value, "gse_controls");
            if (is_named_collection(gse_controls_obj)) {
                for_each_named_item(gse_controls_obj, [&](const std::string& raw_gse_name, const nlohmann::json& gse_val) {
                    std::string gse_name = extract_name_or_fallback(gse_val, raw_gse_name);
                    if (gse_name.empty()) {
                        return;
                    }

                    std::string dataset;
                    if (auto dataset_obj = ipc::codec::find_key(gse_val, "dataset")) {
                        dataset = ipc::codec::as_string(*dataset_obj, "");
                    }

                    std::string app_id;
                    if (auto app_id_obj = ipc::codec::find_key(gse_val, "gocbname")) {
                        app_id = ipc::codec::as_string(*app_id_obj, "");
                    }

                    uint32_t conf_rev = 1;
                    if (auto conf_obj = ipc::codec::find_key(gse_val, "conf_rev")) {
                        conf_rev = static_cast<uint32_t>(ipc::codec::as_int64(*conf_obj, 1));
                    } else if (auto conf_obj = ipc::codec::find_key(gse_val, "confRev")) {
                        conf_rev = static_cast<uint32_t>(ipc::codec::as_int64(*conf_obj, 1));
                    }

                    bool fixed_offs = false;
                    if (auto fixed_obj = ipc::codec::find_key(gse_val, "fixedOffs")) {
                        fixed_offs = object_truthy(*fixed_obj);
                    } else if (auto fixed_obj = ipc::codec::find_key(gse_val, "fixed_offsets")) {
                        fixed_offs = object_truthy(*fixed_obj);
                    }

                    int min_time = -1;
                    int max_time = -1;
                    if (auto min_obj = ipc::codec::find_key(gse_val, "min_time")) {
                        min_time = static_cast<int>(ipc::codec::as_int64(*min_obj, -1));
                    }
                    if (auto max_obj = ipc::codec::find_key(gse_val, "max_time")) {
                        max_time = static_cast<int>(ipc::codec::as_int64(*max_obj, -1));
                    }
                    if (max_time < 0) {
                        if (auto ttl_obj = ipc::codec::find_key(gse_val, "time_allowed_to_live")) {
                            max_time = static_cast<int>(ipc::codec::as_int64(*ttl_obj, -1));
                        }
                    }

                    const char* app_id_ptr = app_id.empty() ? nullptr : app_id.c_str();
                    const char* dataset_ptr = dataset.empty() ? nullptr : dataset.c_str();

                    GSEControlBlock* gse = GSEControlBlock_create(gse_name.c_str(), ln, app_id_ptr, dataset_ptr,
                                                                  conf_rev, fixed_offs, min_time, max_time);
                    gse_controls[ld_name + "/" + gse_name] = gse;
                });
            }

            auto smv_controls_obj = ipc::codec::find_key(ln_value, "smv_controls");
            if (is_named_collection(smv_controls_obj)) {
                for_each_named_item(smv_controls_obj, [&](const std::string& raw_smv_name, const nlohmann::json& smv_val) {
                    std::string smv_name = extract_name_or_fallback(smv_val, raw_smv_name);
                    if (smv_name.empty()) {
                        return;
                    }

                    std::string dataset;
                    if (auto dataset_obj = ipc::codec::find_key(smv_val, "dataset")) {
                        dataset = ipc::codec::as_string(*dataset_obj, "");
                    }

                    std::string sv_id;
                    if (auto id_obj = ipc::codec::find_key(smv_val, "smvcbname")) {
                        sv_id = ipc::codec::as_string(*id_obj, "");
                    }

                    uint32_t conf_rev = 1;
                    if (auto conf_obj = ipc::codec::find_key(smv_val, "conf_rev")) {
                        conf_rev = static_cast<uint32_t>(ipc::codec::as_int64(*conf_obj, 1));
                    } else if (auto conf_obj = ipc::codec::find_key(smv_val, "confRev")) {
                        conf_rev = static_cast<uint32_t>(ipc::codec::as_int64(*conf_obj, 1));
                    }

                    uint8_t smp_mod = IEC61850_SV_SMPMOD_SAMPLES_PER_PERIOD;
                    if (auto mod_obj = ipc::codec::find_key(smv_val, "smpmod")) {
                        std::string mod = ipc::codec::as_string(*mod_obj, "");
                        if (mod == "SmpPerSec") {
                            smp_mod = IEC61850_SV_SMPMOD_SAMPLES_PER_SECOND;
                        } else if (mod == "SmpPerPeriod") {
                            smp_mod = IEC61850_SV_SMPMOD_SAMPLES_PER_PERIOD;
                        } else if (mod == "SecPerSample") {
                            smp_mod = IEC61850_SV_SMPMOD_SECONDS_PER_SAMPLE;
                        }
                    }

                    uint16_t smp_rate = 0;
                    if (auto rate_obj = ipc::codec::find_key(smv_val, "smprate")) {
                        smp_rate = static_cast<uint16_t>(ipc::codec::as_int64(*rate_obj, 0));
                    }

                    uint8_t opt_flds = 0;
                    auto options_obj = ipc::codec::find_key(smv_val, "options");
                    if (options_obj && options_obj->is_object()) {
                        if (auto opt = ipc::codec::find_key(*options_obj, "sampleSync"); opt && object_truthy(*opt)) opt_flds |= IEC61850_SV_OPT_SAMPLE_SYNC;
                        if (auto opt = ipc::codec::find_key(*options_obj, "sampleRate"); opt && object_truthy(*opt)) opt_flds |= IEC61850_SV_OPT_SAMPLE_RATE;
                        if (auto opt = ipc::codec::find_key(*options_obj, "security"); opt && object_truthy(*opt)) opt_flds |= IEC61850_SV_OPT_SECURITY;
                        if (auto opt = ipc::codec::find_key(*options_obj, "dataSet"); opt && object_truthy(*opt)) opt_flds |= IEC61850_SV_OPT_DATA_SET;
                        if (auto opt = ipc::codec::find_key(*options_obj, "refreshTime"); opt && object_truthy(*opt)) opt_flds |= IEC61850_SV_OPT_REFRESH_TIME;
                    }

                    bool is_unicast = false;
                    if (auto unicast_obj = ipc::codec::find_key(smv_val, "unicast")) {
                        is_unicast = object_truthy(*unicast_obj);
                    } else if (auto unicast_obj = ipc::codec::find_key(smv_val, "is_unicast")) {
                        is_unicast = object_truthy(*unicast_obj);
                    }

                    const char* sv_id_ptr = sv_id.empty() ? nullptr : sv_id.c_str();
                    const char* dataset_ptr = dataset.empty() ? nullptr : dataset.c_str();

                    SVControlBlock* smv = SVControlBlock_create(smv_name.c_str(), ln, sv_id_ptr, dataset_ptr,
                                                                conf_rev, smp_mod, smp_rate, opt_flds, is_unicast);
                    smv_controls[ld_name + "/" + smv_name] = smv;
                });
            }

            auto log_controls_obj = ipc::codec::find_key(ln_value, "log_controls");
            if (is_named_collection(log_controls_obj)) {
                for_each_named_item(log_controls_obj, [&](const std::string& raw_log_name, const nlohmann::json& log_val) {
                    std::string log_name = extract_name_or_fallback(log_val, raw_log_name);
                    if (log_name.empty()) {
                        return;
                    }

                    std::string dataset;
                    if (auto dataset_obj = ipc::codec::find_key(log_val, "dataset")) {
                        dataset = ipc::codec::as_string(*dataset_obj, "");
                    }

                    std::string log_ref;
                    if (auto ref_obj = ipc::codec::find_key(log_val, "logname")) {
                        log_ref = ipc::codec::as_string(*ref_obj, "");
                    }

                    bool log_ena = false;
                    if (auto ena_obj = ipc::codec::find_key(log_val, "log_ena")) {
                        log_ena = object_truthy(*ena_obj);
                    }

                    uint32_t intg_pd = 0;
                    if (auto intg_obj = ipc::codec::find_key(log_val, "intg_pd")) {
                        intg_pd = static_cast<uint32_t>(ipc::codec::as_int64(*intg_obj, 0));
                    }

                    uint8_t trg_ops = 0;
                    bool with_reason_code = false;
                    auto options_obj = ipc::codec::find_key(log_val, "options");
                    if (options_obj && options_obj->is_object()) {
                        if (auto opt = ipc::codec::find_key(*options_obj, "dataChange"); opt && object_truthy(*opt)) trg_ops |= TRG_OPT_DATA_CHANGED;
                        if (auto opt = ipc::codec::find_key(*options_obj, "qualityChange"); opt && object_truthy(*opt)) trg_ops |= TRG_OPT_QUALITY_CHANGED;
                        if (auto opt = ipc::codec::find_key(*options_obj, "dataUpdate"); opt && object_truthy(*opt)) trg_ops |= TRG_OPT_DATA_UPDATE;
                        if (auto opt = ipc::codec::find_key(*options_obj, "integrityCheck"); opt && object_truthy(*opt)) trg_ops |= TRG_OPT_INTEGRITY;
                        if (auto opt = ipc::codec::find_key(*options_obj, "reasonForInclusion")) {
                            with_reason_code = object_truthy(*opt);
                        }
                    }

                    const char* dataset_ptr = dataset.empty() ? nullptr : dataset.c_str();
                    const char* log_ref_ptr = log_ref.empty() ? nullptr : log_ref.c_str();
                    LogControlBlock_create(log_name.c_str(), ln, dataset_ptr, log_ref_ptr, trg_ops,
                                           intg_pd, log_ena, with_reason_code);

                    if (!log_ref.empty() && !log_instances.count(log_ref)) {
                        log_instances[log_ref] = Log_create(log_ref.c_str(), ln);
                    }
                });
            }

            auto sg_obj = ipc::codec::find_key(ln_value, "setting_group_control");
            if (sg_obj && sg_obj->is_object() && ln_name == "LLN0") {
                uint8_t act_sg = 1;
                uint8_t num_sgs = 1;
                if (auto act_obj = ipc::codec::find_key(*sg_obj, "act_sg")) {
                    act_sg = static_cast<uint8_t>(ipc::codec::as_int64(*act_obj, 1));
                }
                if (auto num_obj = ipc::codec::find_key(*sg_obj, "num_of_sgs")) {
                    num_sgs = static_cast<uint8_t>(ipc::codec::as_int64(*num_obj, 1));
                }
                SettingGroupControlBlock_create(ln, act_sg, num_sgs);
            }
        });
    });

    auto comm_obj = ipc::codec::find_key(model_obj, "communication");
    if (comm_obj && comm_obj->is_object()) {
        for (auto ap_it = comm_obj->begin(); ap_it != comm_obj->end(); ++ap_it) {
            const auto& ap_obj = ap_it.value();
            if (!ap_obj.is_object()) {
                continue;
            }

            if (auto gse_addr_obj = ipc::codec::find_key(ap_obj, "gse_addresses"); gse_addr_obj && gse_addr_obj->is_object()) {
                for (auto gse_addr_it = gse_addr_obj->begin(); gse_addr_it != gse_addr_obj->end(); ++gse_addr_it) {
                    std::string gse_key = gse_addr_it.key();
                    auto gse_it = gse_controls.find(gse_key);
                    if (gse_it == gse_controls.end()) {
                        continue;
                    }

                    const auto& addr_obj = gse_addr_it.value();
                    if (!addr_obj.is_object()) {
                        continue;
                    }

                    uint8_t mac[6] = {0};
                    auto mac_obj = ipc::codec::find_key(addr_obj, "mac_address");
                    if (!mac_obj || !parse_hex_bytes(ipc::codec::as_string(*mac_obj, ""), mac, sizeof(mac))) {
                        continue;
                    }

                    uint32_t app_id = 0;
                    if (auto app_obj = ipc::codec::find_key(addr_obj, "appid")) {
                        app_id = parse_uint32_hex_default(*app_obj);
                    }

                    uint32_t vlan_prio = 0;
                    if (auto prio_obj = ipc::codec::find_key(addr_obj, "vlan_priority")) {
                        vlan_prio = static_cast<uint32_t>(ipc::codec::as_int64(*prio_obj, 0));
                    }

                    uint32_t vlan_id = 0;
                    if (auto vlan_obj = ipc::codec::find_key(addr_obj, "vlan_id")) {
                        vlan_id = parse_uint32_auto_base(*vlan_obj);
                    }

                    PhyComAddress* dst_address = PhyComAddress_create(static_cast<uint8_t>(vlan_prio),
                                                                      static_cast<uint16_t>(vlan_id),
                                                                      static_cast<uint16_t>(app_id),
                                                                      mac);
                    GSEControlBlock_addPhyComAddress(gse_it->second, dst_address);
                }
            }

            if (auto smv_addr_obj = ipc::codec::find_key(ap_obj, "smv_addresses"); smv_addr_obj && smv_addr_obj->is_object()) {
                for (auto smv_addr_it = smv_addr_obj->begin(); smv_addr_it != smv_addr_obj->end(); ++smv_addr_it) {
                    std::string smv_key = smv_addr_it.key();
                    auto smv_it = smv_controls.find(smv_key);
                    if (smv_it == smv_controls.end()) {
                        continue;
                    }

                    const auto& addr_obj = smv_addr_it.value();
                    if (!addr_obj.is_object()) {
                        continue;
                    }

                    uint8_t mac[6] = {0};
                    auto mac_obj = ipc::codec::find_key(addr_obj, "mac_address");
                    if (!mac_obj || !parse_hex_bytes(ipc::codec::as_string(*mac_obj, ""), mac, sizeof(mac))) {
                        continue;
                    }

                    uint32_t app_id = 0;
                    if (auto app_obj = ipc::codec::find_key(addr_obj, "appid")) {
                        app_id = parse_uint32_hex_default(*app_obj);
                    }

                    uint32_t vlan_prio = 0;
                    if (auto prio_obj = ipc::codec::find_key(addr_obj, "vlan_priority")) {
                        vlan_prio = static_cast<uint32_t>(ipc::codec::as_int64(*prio_obj, 0));
                    }

                    uint32_t vlan_id = 0;
                    if (auto vlan_obj = ipc::codec::find_key(addr_obj, "vlan_id")) {
                        vlan_id = parse_uint32_auto_base(*vlan_obj);
                    }

                    PhyComAddress* dst_address = PhyComAddress_create(static_cast<uint8_t>(vlan_prio),
                                                                      static_cast<uint16_t>(vlan_id),
                                                                      static_cast<uint16_t>(app_id),
                                                                      mac);
                    SVControlBlock_addPhyComAddress(smv_it->second, dst_address);
                }
            }
        }
    }

    return model;
}

} // namespace

bool ServerLoadModelAction::handle(ActionContext& ctx, nlohmann::json& response) {
    if (!check_payload_existence(ctx, response)) {
        return true;
    }

    std::lock_guard<std::mutex> lock(ctx.context.mutex);

    bool error_occurred = false;
    std::string instance_id = validate_and_extract_instance_id(ctx.payload, ctx.action, response, error_occurred);
    if (error_occurred) {
        return true;
    }

    LOG4CPLUS_INFO(server_logger(), "server.load_model requested for instance " << instance_id);

    auto model_obj = ipc::codec::find_key(ctx.payload, "model");
    auto config_obj = ipc::codec::find_key(ctx.payload, "config");

    if (!model_obj) {
        LOG4CPLUS_ERROR(server_logger(), "server.load_model: model is required for instance " << instance_id);
        pack_error_response(response, "model payload is required");
        return true;
    }

    auto* inst = ctx.context.get_or_create_server_instance(instance_id);

    if (inst->server) {
        IedServer_stop(inst->server);
        IedServer_destroy(inst->server);
        inst->server = nullptr;
    }
    if (inst->config) {
        IedServerConfig_destroy(inst->config);
        inst->config = nullptr;
    }
    if (inst->model) {
        IedModel_destroy(inst->model);
        inst->model = nullptr;
    }

    inst->model = build_model_from_json(*model_obj, inst->ied_name);

    inst->config = IedServerConfig_create();

    int max_conn = 10;
    int port = 102;
    std::string ip_address = "0.0.0.0";

    if (config_obj && config_obj->is_object()) {
        if (auto max_conn_obj = ipc::codec::find_key(*config_obj, "max_connections")) {
            max_conn = static_cast<int>(ipc::codec::as_int64(*max_conn_obj, 10));
            LOG4CPLUS_DEBUG(server_logger(), "max_connections set to " << max_conn);
        }
        if (auto port_obj = ipc::codec::find_key(*config_obj, "port")) {
            port = static_cast<int>(ipc::codec::as_int64(*port_obj, 102));
            LOG4CPLUS_DEBUG(server_logger(), "port set to " << port);
        }
        if (auto ip_obj = ipc::codec::find_key(*config_obj, "ip_address")) {
            ip_address = ipc::codec::as_string(*ip_obj, "0.0.0.0");
            LOG4CPLUS_DEBUG(server_logger(), "ip_address set to " << ip_address);
        }
    }

    IedServerConfig_setMaxMmsConnections(inst->config, max_conn);

    inst->port = port;
    inst->ip_address = ip_address;

    LOG4CPLUS_INFO(server_logger(), "Server instance " << instance_id << " loaded model (" << inst->ied_name << "), ready to start on " << ip_address << ":" << port);

    response["result"] = {
        {"success", true},
        {"instance_id", instance_id},
    };
    response["error"] = nullptr;
    return true;
}

} // namespace ipc::actions
