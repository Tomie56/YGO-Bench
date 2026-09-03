#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


BULK_CARD_LOADER = """inline void preload_all_cards(
    const SQLite::Database &db, const std::vector<CardCode> &codes) {
  SQLite::Statement query(
      db,
      "SELECT d.id, d.alias, d.setcode, d.type, d.atk, d.def, d.level, "
      "d.race, d.attribute, t.name, t.desc, t.str1, t.str2, t.str3, "
      "t.str4, t.str5, t.str6, t.str7, t.str8, t.str9, t.str10, t.str11, "
      "t.str12, t.str13, t.str14, t.str15, t.str16 "
      "FROM datas d JOIN texts t ON t.id = d.id "
      "WHERE d.id > 0 ORDER BY d.id");
  size_t loaded = 0;
  while (query.executeStep()) {
    CardCode code = query.getColumn(0);
    if (loaded >= codes.size() || codes[loaded] != code) {
      throw std::runtime_error(
          "Code list and BabelCDB order differ at card: " +
          std::to_string(code));
    }

    uint32_t alias = query.getColumn(1);
    uint64_t packed_setcodes = query.getColumn(2).getInt64();
    uint32_t type = query.getColumn(3);
    int32_t attack = query.getColumn(4);
    int32_t raw_defense = query.getColumn(5);
    int32_t raw_level = query.getColumn(6);
    uint32_t level_bits = static_cast<uint32_t>(raw_level);
    uint32_t level = level_bits & 0xff;
    uint32_t lscale = (level_bits >> 24) & 0xff;
    uint32_t rscale = (level_bits >> 16) & 0xff;
    uint64_t race = query.getColumn(7).getInt64();
    uint32_t attribute = query.getColumn(8);
    int32_t defense = raw_defense;
    uint32_t link_marker = 0;
    if (type & TYPE_LINK) {
      link_marker = static_cast<uint32_t>(raw_defense);
      defense = 0;
    }

    std::string name = query.getColumn(9);
    std::string desc = query.getColumn(10);
    std::vector<std::string> strings;
    strings.reserve(16);
    for (int column = 11; column < query.getColumnCount(); ++column) {
      strings.emplace_back(query.getColumn(column));
    }
    cards_[code] = Card(
        code, alias, type, level, lscale, rscale, attack, defense,
        static_cast<uint32_t>(race), attribute, link_marker, name, desc,
        strings);

    OCG_CardData card_data{};
    card_data.code = code;
    card_data.alias = alias;
    std::vector<uint16_t> setcodes;
    for (int offset = 0; offset < 4; ++offset) {
      uint16_t setcode = (packed_setcodes >> (offset * 16)) & 0xffff;
      if (setcode != 0) {
        setcodes.push_back(setcode);
      }
    }
    if (!setcodes.empty()) {
      setcodes.push_back(0);
      card_data.setcodes = new uint16_t[setcodes.size()];
      std::copy(setcodes.begin(), setcodes.end(), card_data.setcodes);
    }
    card_data.type = type;
    card_data.attack = attack;
    card_data.defense = raw_defense;
    card_data.link_marker = 0;
    if (type & TYPE_LINK) {
      card_data.link_marker = static_cast<uint32_t>(raw_defense);
      card_data.defense = 0;
    }
    card_data.level = raw_level < 0 ? -(raw_level & 0xff) : raw_level & 0xff;
    card_data.lscale = lscale;
    card_data.rscale = rscale;
    card_data.race = race;
    card_data.attribute = attribute;
    cards_data_[code] = card_data;
    ++loaded;
  }
  if (loaded != codes.size()) {
    throw std::runtime_error(
        "Code list contains cards missing from BabelCDB: " +
        std::to_string(codes.size() - loaded));
  }
}"""


MODERN_QUERY_READER = """  using QueryFields = std::map<uint32_t, std::vector<uint8_t>>;

  bool parse_query_record(const uint8_t* buffer, size_t length, size_t& offset,
                          QueryFields& fields) {
    fields.clear();
    if (offset + sizeof(uint16_t) > length) {
      throw std::runtime_error("Truncated query record length");
    }
    uint16_t field_size = 0;
    std::memcpy(&field_size, buffer + offset, sizeof(field_size));
    offset += sizeof(field_size);
    if (field_size == 0) {
      return false;
    }

    while (true) {
      if (field_size < sizeof(uint32_t) || offset + field_size > length) {
        throw std::runtime_error("Invalid query field size: " +
                                 std::to_string(field_size));
      }
      uint32_t flag = 0;
      std::memcpy(&flag, buffer + offset, sizeof(flag));
      offset += sizeof(flag);
      const size_t payload_size = field_size - sizeof(flag);
      if (flag == QUERY_END) {
        if (payload_size != 0) {
          throw std::runtime_error("QUERY_END has a non-empty payload");
        }
        return true;
      }
      std::vector<uint8_t> payload(
          buffer + offset, buffer + offset + payload_size);
      if (!fields.emplace(flag, std::move(payload)).second) {
        throw std::runtime_error("Duplicate query field: " +
                                 std::to_string(flag));
      }
      offset += payload_size;
      if (offset + sizeof(uint16_t) > length) {
        throw std::runtime_error("Query record is missing QUERY_END");
      }
      std::memcpy(&field_size, buffer + offset, sizeof(field_size));
      offset += sizeof(field_size);
    }
  }

  const std::vector<uint8_t>& query_payload(const QueryFields& fields,
                                             uint32_t flag) {
    auto field = fields.find(flag);
    if (field == fields.end()) {
      throw std::runtime_error("Required query field missing: " +
                               std::to_string(flag));
    }
    return field->second;
  }

  uint32_t query_u32(const QueryFields& fields, uint32_t flag) {
    const auto& payload = query_payload(fields, flag);
    if (payload.size() != sizeof(uint32_t)) {
      throw std::runtime_error("Query field has invalid uint32 payload: " +
                               std::to_string(flag));
    }
    uint32_t value = 0;
    std::memcpy(&value, payload.data(), sizeof(value));
    return value;
  }

  Card card_from_query(const QueryFields& fields, PlayerId player, uint8_t loc,
                       uint32_t sequence) {
    Card c = c_get_card(query_u32(fields, QUERY_CODE));
    c.controler_ = player;
    c.location_ = loc;
    c.sequence_ = sequence;
    c.position_ = query_u32(fields, QUERY_POSITION);
    const uint32_t level = query_u32(fields, QUERY_LEVEL);
    if ((level & 0xff) > 0) {
      c.level_ = level & 0xff;
    }
    const uint32_t rank = query_u32(fields, QUERY_RANK);
    if ((rank & 0xff) > 0) {
      c.level_ = rank & 0xff;
    }
    c.attack_ = query_u32(fields, QUERY_ATTACK);
    c.defense_ = query_u32(fields, QUERY_DEFENSE);
    c.lscale_ = query_u32(fields, QUERY_LSCALE);
    c.rscale_ = query_u32(fields, QUERY_RSCALE);

    const auto& link = query_payload(fields, QUERY_LINK);
    if (link.size() != 2 * sizeof(uint32_t)) {
      throw std::runtime_error("QUERY_LINK has an invalid payload size");
    }
    uint32_t link_level = 0;
    uint32_t link_marker = 0;
    std::memcpy(&link_level, link.data(), sizeof(link_level));
    std::memcpy(&link_marker, link.data() + sizeof(link_level),
                sizeof(link_marker));
    if ((link_level & 0xff) > 0) {
      c.level_ = link_level & 0xff;
    }
    if (link_marker > 0) {
      c.defense_ = link_marker;
    }
    return c;
  }

  CardCode get_card_code(PlayerId player, uint8_t loc, uint8_t seq) {
    const uint32_t flags = QUERY_CODE;
    const int32_t length =
        YGO_QueryCard(pduel_, player, loc, seq, flags, query_buf_);
    if (length <= 0) {
      throw std::runtime_error("[get_card_code] Invalid card");
    }
    size_t offset = 0;
    QueryFields fields;
    if (!parse_query_record(query_buf_, length, offset, fields)) {
      throw std::runtime_error("[get_card_code] Empty query record");
    }
    if (offset != static_cast<size_t>(length)) {
      throw std::runtime_error("[get_card_code] Trailing query bytes");
    }
    return query_u32(fields, QUERY_CODE);
  }

  Card get_card(PlayerId player, uint8_t loc, uint8_t seq) {
    const uint32_t flags =
        QUERY_CODE | QUERY_POSITION | QUERY_LEVEL | QUERY_RANK |
        QUERY_ATTACK | QUERY_DEFENSE | QUERY_LSCALE | QUERY_RSCALE |
        QUERY_LINK;
    const int32_t length =
        YGO_QueryCard(pduel_, player, loc, seq, flags, query_buf_);
    if (length <= 0) {
      throw std::runtime_error(fmt::format(
          "[get_card] Invalid card: player={}, loc={}, seq={}, length={}",
          player, loc, seq, length));
    }
    size_t offset = 0;
    QueryFields fields;
    if (!parse_query_record(query_buf_, length, offset, fields)) {
      throw std::runtime_error("[get_card] Empty query record");
    }
    if (offset != static_cast<size_t>(length)) {
      throw std::runtime_error("[get_card] Trailing query bytes");
    }
    return card_from_query(fields, player, loc, seq);
  }

  std::vector<Card> get_cards_in_location(PlayerId player, uint8_t loc) {
    const uint32_t flags =
        QUERY_CODE | QUERY_POSITION | QUERY_LEVEL | QUERY_RANK |
        QUERY_ATTACK | QUERY_DEFENSE | QUERY_EQUIP_CARD |
        QUERY_OVERLAY_CARD | QUERY_COUNTERS | QUERY_LSCALE |
        QUERY_RSCALE | QUERY_LINK;
    const int32_t length =
        OCG_QueryFieldCard(pduel_, player, loc, flags, query_buf_, 0);
    if (length < static_cast<int32_t>(sizeof(uint32_t))) {
      throw std::runtime_error("Location query is missing its size header");
    }
    uint32_t payload_size = 0;
    std::memcpy(&payload_size, query_buf_, sizeof(payload_size));
    if (payload_size != static_cast<uint32_t>(length - sizeof(uint32_t))) {
      throw std::runtime_error("Location query size header does not match buffer");
    }

    size_t offset = sizeof(uint32_t);
    uint32_t sequence = 0;
    std::vector<Card> cards;
    while (offset < static_cast<size_t>(length)) {
      QueryFields fields;
      const bool present =
          parse_query_record(query_buf_, length, offset, fields);
      if (!present) {
        ++sequence;
        continue;
      }
      Card c = card_from_query(fields, player, loc, sequence);

      const auto& overlays = query_payload(fields, QUERY_OVERLAY_CARD);
      if (overlays.size() < sizeof(uint32_t)) {
        throw std::runtime_error("QUERY_OVERLAY_CARD payload is truncated");
      }
      uint32_t overlay_count = 0;
      std::memcpy(&overlay_count, overlays.data(), sizeof(overlay_count));
      if (overlays.size() !=
          sizeof(uint32_t) * static_cast<size_t>(overlay_count + 1)) {
        throw std::runtime_error("QUERY_OVERLAY_CARD count does not match payload");
      }
      for (uint32_t index = 0; index < overlay_count; ++index) {
        CardCode code = 0;
        std::memcpy(&code,
                    overlays.data() + sizeof(uint32_t) * (index + 1),
                    sizeof(code));
        Card overlay = c_get_card(code);
        overlay.controler_ = player;
        overlay.location_ = loc | LOCATION_OVERLAY;
        overlay.sequence_ = sequence;
        overlay.position_ = index;
        cards.push_back(overlay);
      }

      const auto& counters = query_payload(fields, QUERY_COUNTERS);
      if (counters.size() < sizeof(uint32_t)) {
        throw std::runtime_error("QUERY_COUNTERS payload is truncated");
      }
      uint32_t counter_count = 0;
      std::memcpy(&counter_count, counters.data(), sizeof(counter_count));
      if (counters.size() !=
          sizeof(uint32_t) * static_cast<size_t>(counter_count + 1)) {
        throw std::runtime_error("QUERY_COUNTERS count does not match payload");
      }
      if (counter_count > 0) {
        std::memcpy(&c.counter_, counters.data() + sizeof(uint32_t),
                    sizeof(c.counter_));
      }

      cards.push_back(c);
      ++sequence;
    }
    return cards;
  }"""


REPLACEMENTS = (
    (
        "explicit standard-library includes",
        "#include <fstream>\n#include <shared_mutex>",
        "#include <fstream>\n#include <cctype>\n#include <filesystem>\n"
        "#include <limits>\n#include <shared_mutex>\n#include <sstream>\n"
        "#include <unordered_set>",
    ),
    (
        "selection-aware private deck identities",
        "  void _set_obs_cards(TArray<uint8_t> &f_cards, SpecIndex &spec2index,\n"
        "                      PlayerId to_play) {\n"
        "    for (auto pi = 0; pi < 2; pi++) {",
        "  void _set_obs_cards(TArray<uint8_t> &f_cards, SpecIndex &spec2index,\n"
        "                      PlayerId to_play,\n"
        "                      TArray<uint8_t> &f_visibility) {\n"
        "    constexpr uint8_t kHiddenPrivate = 1;\n"
        "    constexpr uint8_t kOwnerVisible = 2;\n"
        "    constexpr uint8_t kPublicField = 3;\n"
        "    constexpr uint8_t kConfirmedReveal = 4;\n"
        "    constexpr uint8_t kSelectableOwnDeck = 5;\n"
        "    constexpr uint8_t kOpponentFacedown = 6;\n"
        "    std::unordered_set<std::string> selectable_specs;\n"
        "    if (msg_ == MSG_SELECT_CARD || msg_ == MSG_SELECT_TRIBUTE ||\n"
        "        msg_ == MSG_SELECT_SUM || msg_ == MSG_SELECT_UNSELECT_CARD) {\n"
        "      for (const auto &option : options_) {\n"
        "        std::istringstream stream(option);\n"
        "        std::string spec;\n"
        "        while (stream >> spec) {\n"
        "          if (spec != \"c\" && spec != \"f\") {\n"
        "            selectable_specs.insert(spec);\n"
        "          }\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "    for (auto pi = 0; pi < 2; pi++) {",
    ),
    (
        "card visibility audit state",
        "        \"obs:h_actions_\"_.Bind(\n"
        "            Spec<uint8_t>({conf[\"n_history_actions\"_], n_action_feats})),\n"
        "        \"info:num_options\"_.Bind(Spec<int>({}, {0, conf[\"max_options\"_] - 1})),",
        "        \"obs:h_actions_\"_.Bind(\n"
        "            Spec<uint8_t>({conf[\"n_history_actions\"_], n_action_feats})),\n"
        "        \"info:card_visibility_\"_.Bind(\n"
        "            Spec<uint8_t>({conf[\"max_cards\"_] * 2})),\n"
        "        \"info:num_options\"_.Bind(Spec<int>({}, {0, conf[\"max_options\"_] - 1})),",
    ),
    (
        "private-zone reveal provenance",
        "        // check this\n"
        "        if (opponent && (location == LOCATION_HAND) &&\n"
        "            (revealed_.size() != 0)) {\n"
        "          hidden_for_opponent = false;\n"
        "        }\n"
        "        if (opponent && hidden_for_opponent) {\n"
        "          auto n_cards = YGO_QueryFieldCount(pduel_, player, location);\n"
        "          for (auto i = 0; i < n_cards; i++) {\n"
        "            f_cards(offset, 2) = location2id.at(location);\n"
        "            f_cards(offset, 4) = 1;\n"
        "            offset++;\n"
        "          }\n"
        "        } else {",
        "        if (opponent && hidden_for_opponent && revealed_.empty()) {\n"
        "          auto n_cards = YGO_QueryFieldCount(pduel_, player, location);\n"
        "          for (auto i = 0; i < n_cards; i++) {\n"
        "            f_cards(offset, 2) = location2id.at(location);\n"
        "            f_cards(offset, 4) = 1;\n"
        "            f_visibility(offset) = kHiddenPrivate;\n"
        "            offset++;\n"
        "          }\n"
        "        } else {",
    ),
    (
        "hide shuffled own-deck order",
        "            bool hide = false;\n"
        "            if (opponent) {\n"
        "              hide = c.position_ & POS_FACEDOWN;\n"
        "              if ((location == LOCATION_HAND) &&\n"
        "                  (std::find(revealed_.begin(), revealed_.end(), spec) !=\n"
        "                   revealed_.end())) {\n"
        "                hide = false;\n"
        "              }\n"
        "            }",
        "            const bool confirmed_visible =\n"
        "                std::find(revealed_.begin(), revealed_.end(), spec) !=\n"
        "                revealed_.end();\n"
        "            const bool selectable_own_deck_card =\n"
        "                !opponent && location == LOCATION_DECK &&\n"
        "                selectable_specs.find(spec) != selectable_specs.end();\n"
        "            const bool opponent_private =\n"
        "                opponent && (location == LOCATION_DECK ||\n"
        "                             location == LOCATION_HAND ||\n"
        "                             location == LOCATION_EXTRA);\n"
        "            const bool opponent_facedown =\n"
        "                opponent && (c.position_ & POS_FACEDOWN);\n"
        "            bool hide =\n"
        "                ((location == LOCATION_DECK) || opponent_private ||\n"
        "                 opponent_facedown) &&\n"
        "                !confirmed_visible && !selectable_own_deck_card;\n"
        "            if (opponent) {\n"
        "              if (confirmed_visible) {\n"
        "                hide = false;\n"
        "              }\n"
        "            }\n"
        "            uint8_t visibility = kHiddenPrivate;\n"
        "            if (confirmed_visible) {\n"
        "              visibility = kConfirmedReveal;\n"
        "            } else if (selectable_own_deck_card) {\n"
        "              visibility = kSelectableOwnDeck;\n"
        "            } else if (!opponent && location != LOCATION_DECK) {\n"
        "              visibility = kOwnerVisible;\n"
        "            } else if (opponent_facedown && !opponent_private) {\n"
        "              visibility = kOpponentFacedown;\n"
        "            } else if (opponent && !opponent_private) {\n"
        "              visibility = kPublicField;\n"
        "            }\n"
        "            f_visibility(offset) = visibility;",
    ),
    (
        "write card visibility audit state",
        "    _set_obs_cards(state[\"obs:cards_\"_], spec2index, to_play_);",
        "    _set_obs_cards(state[\"obs:cards_\"_], spec2index, to_play_,\n"
        "                   state[\"info:card_visibility_\"_]);",
    ),
    (
        "EDOPro API v11 duel options pointer",
        "OCG_CreateDuel(&pduel_, opts)",
        "OCG_CreateDuel(&pduel_, &opts)",
    ),
    (
        "zero-initialized duel options",
        "    OCG_DuelOptions opts;",
        "    OCG_DuelOptions opts{};",
    ),
    (
        "specific duel creation status",
        '      throw std::runtime_error("Failed to create duel");',
        '      throw std::runtime_error("Failed to create duel, status=" +\n'
        "                               std::to_string(create_status));",
    ),
    (
        "EDOPro API v11 new-card pointer",
        "OCG_DuelNewCard(pduel, info)",
        "OCG_DuelNewCard(pduel, &info)",
    ),
    (
        "EDOPro API v11 card-query pointer",
        "OCG_DuelQuery(pduel, &length, info)",
        "OCG_DuelQuery(pduel, &length, &info)",
    ),
    (
        "EDOPro API v11 location-query pointer",
        "OCG_DuelQueryLocation(pduel, &length, info)",
        "OCG_DuelQueryLocation(pduel, &length, &info)",
    ),
    (
        "explicit CardScripts state",
        "static std::shared_timed_mutex scripts_mtx;",
        "static std::shared_timed_mutex scripts_mtx;\n"
        "static std::filesystem::path scripts_dir_;\n"
        "static bool module_initialized_ = false;",
    ),
    (
        "diagnostic card lookups",
        "inline const Card &c_get_card(CardCode code) { return cards_.at(code); }\n\n"
        "inline CardId &c_get_card_id(CardCode code) { return card_ids_.at(code); }",
        "inline const Card &c_get_card(CardCode code) {\n"
        "  auto card = cards_.find(code);\n"
        "  if (card == cards_.end()) {\n"
        "    throw std::runtime_error(\"Card metadata missing for code: \" +\n"
        "                             std::to_string(code));\n"
        "  }\n"
        "  return card->second;\n"
        "}\n\n"
        "inline CardId &c_get_card_id(CardCode code) {\n"
        "  auto card_id = card_ids_.find(code);\n"
        "  if (card_id == card_ids_.end()) {\n"
        "    throw std::runtime_error(\"Observation card ID missing for code: \" +\n"
        "                             std::to_string(code));\n"
        "  }\n"
        "  return card_id->second;\n"
        "}",
    ),
    (
        "CardScripts repository layout",
        "  // edopro_script/c*.lua copied from ProjectIgnis/script/official\n"
        "  auto full_path = \"edopro_script/\" + path;",
        "  const bool is_card_script =\n"
        "      path.size() > 5 && path[0] == 'c' &&\n"
        "      std::isdigit(static_cast<unsigned char>(path[1])) &&\n"
        "      path.compare(path.size() - 4, 4, \".lua\") == 0;\n"
        "  auto full_path = scripts_dir_ / path;\n"
        "  if (path == \"proc_unofficial.lua\") {\n"
        "    full_path = scripts_dir_ / \"unofficial\" / path;\n"
        "  } else if (is_card_script) {\n"
        "    full_path = scripts_dir_ / \"official\" / path;\n"
        "    if (!std::filesystem::is_regular_file(full_path)) {\n"
        "      CardCode code = std::stoul(path.substr(1, path.size() - 5));\n"
        "      auto card = cards_data_.find(code);\n"
        "      if (card != cards_data_.end() && card->second.alias != 0) {\n"
        "        full_path = scripts_dir_ / \"official\" /\n"
        "                    (\"c\" + std::to_string(card->second.alias) + \".lua\");\n"
        "      }\n"
        "    }\n"
        "  }",
    ),
    (
        "filesystem path logging",
        'fmt::print("Unable to open script file: {}\\n", full_path);',
        'fmt::print("Unable to open script file: {}\\n", full_path.string());',
    ),
    (
        "explicit scriptless card types",
        "      if (card != cards_data_.end() && card->second.alias != 0) {\n"
        "        full_path = scripts_dir_ / \"official\" /\n"
        "                    (\"c\" + std::to_string(card->second.alias) + \".lua\");\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "  std::ifstream file(full_path, std::ios::binary);",
        "      if (card != cards_data_.end() && card->second.alias != 0) {\n"
        "        full_path = scripts_dir_ / \"official\" /\n"
        "                    (\"c\" + std::to_string(card->second.alias) + \".lua\");\n"
        "      }\n"
        "      if (!std::filesystem::is_regular_file(full_path) &&\n"
        "          card != cards_data_.end()) {\n"
        "        const uint32_t type = card->second.type;\n"
        "        const bool normal_monster =\n"
        "            (type & TYPE_MONSTER) && (type & TYPE_NORMAL) &&\n"
        "            !(type & TYPE_PENDULUM);\n"
        "        if (normal_monster || (type & TYPE_TOKEN)) {\n"
        "          *lenptr = 0;\n"
        "          return nullptr;\n"
        "        }\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "  std::ifstream file(full_path, std::ios::binary);",
    ),
    (
        "explicit core temporary-card sentinel",
        "inline int g_ScriptReader(void* payload, OCG_Duel duel, const char* name) {\n"
        "  std::string path(name);\n"
        "  std::shared_lock<std::shared_timed_mutex> lock(scripts_mtx);",
        "inline int g_ScriptReader(void* payload, OCG_Duel duel, const char* name) {\n"
        "  std::string path(name);\n"
        "  if (path == \"c0.lua\") {\n"
        "    return 0;\n"
        "  }\n"
        "  std::shared_lock<std::shared_timed_mutex> lock(scripts_mtx);",
    ),
    (
        "explicit CardScripts init argument",
        "static void init_module(const std::string &db_path,\n"
        "                        const std::string &code_list_file,\n"
        "                        const std::map<std::string, std::string> &decks) {",
        "static void init_module(\n"
        "    const std::string &db_path, const std::string &code_list_file,\n"
        "    const std::map<std::string, std::string> &decks,\n"
        "    const std::string &script_dir) {\n"
        "  if (module_initialized_) {\n"
        "    throw std::runtime_error(\"EDOPro module is already initialized\");\n"
        "  }\n"
        "  scripts_dir_ = std::filesystem::path(script_dir);\n"
        "  if (!std::filesystem::is_directory(scripts_dir_)) {\n"
        "    throw std::runtime_error(\"CardScripts directory not found: \" + script_dir);\n"
        "  }\n"
        "  for (const auto *name : {\"constant.lua\", \"utility.lua\"}) {\n"
        "    if (!std::filesystem::is_regular_file(scripts_dir_ / name)) {\n"
        "      throw std::runtime_error(\"Required CardScripts file not found: \" +\n"
        "                               (scripts_dir_ / name).string());\n"
        "    }\n"
        "  }",
    ),
    (
        "init input validation",
        "  std::ifstream file(code_list_file);",
        "  std::ifstream file(code_list_file);\n"
        "  if (!file.is_open()) {\n"
        "    throw std::runtime_error(\"Code list not found: \" + code_list_file);\n"
        "  }\n"
        "  if (decks.empty()) {\n"
        "    throw std::runtime_error(\"At least one deck is required\");\n"
        "  }\n"
        "  std::vector<CardCode> all_codes;",
    ),
    (
        "stable code-list validation",
        "  while (std::getline(file, line)) {\n"
        "    i++;\n"
        "    CardCode code = std::stoul(line);\n"
        "    card_ids_[code] = i;\n"
        "  }",
        "  while (std::getline(file, line)) {\n"
        "    CardCode code = std::stoul(line);\n"
        "    i++;\n"
        "    if (i > std::numeric_limits<CardId>::max()) {\n"
        "      throw std::runtime_error(\"Code list exceeds uint16 card ID capacity\");\n"
        "    }\n"
        "    if (!card_ids_.emplace(code, i).second) {\n"
        "      throw std::runtime_error(\"Duplicate card in code list: \" +\n"
        "                               std::to_string(code));\n"
        "    }\n"
        "    all_codes.push_back(code);\n"
        "  }",
    ),
    (
        "bulk BabelCDB loader",
        "inline void preload_deck(const SQLite::Database &db,",
        BULK_CARD_LOADER
        + "\n\ninline void preload_deck(const SQLite::Database &db,",
    ),
    (
        "full BabelCDB preload",
        "  SQLite::Database db(db_path, SQLite::OPEN_READONLY);\n\n"
        "  for (const auto &[name, deck] : decks) {",
        "  SQLite::Database db(db_path, SQLite::OPEN_READONLY);\n"
        "  preload_all_cards(db, all_codes);\n\n"
        "  for (const auto &[name, deck] : decks) {",
    ),
    (
        "non-empty deck names",
        "  for (const auto &[name, deck] : decks) {\n"
        "    auto [main_deck, extra_deck, side_deck] = read_decks(deck);",
        "  for (const auto &[name, deck] : decks) {\n"
        "    if (name.empty()) {\n"
        "      throw std::runtime_error(\"Deck name must not be empty\");\n"
        "    }\n"
        "    auto [main_deck, extra_deck, side_deck] = read_decks(deck);",
    ),
    (
        "successful init marker",
        "  for (auto &[name, deck] : extra_decks_) {\n"
        "    sort_extra_deck(deck);\n"
        "  }\n\n"
        "}",
        "  for (auto &[name, deck] : extra_decks_) {\n"
        "    sort_extra_deck(deck);\n"
        "  }\n"
        "  module_initialized_ = true;\n\n"
        "}",
    ),
    (
        "initialized duel and player pointers",
        "  OCG_Duel pduel_;\n  Player *players_[2]; //  abstract class must be pointer",
        "  OCG_Duel pduel_{nullptr};\n"
        "  Player *players_[2]{nullptr, nullptr};",
    ),
    (
        "safe environment destructor",
        "  ~EDOProEnv() {\n"
        "    for (int i = 0; i < 2; i++) {\n"
        "      if (players_[i] != nullptr) {\n"
        "        delete players_[i];\n"
        "      }\n"
        "    }\n"
        "  }",
        "  ~EDOProEnv() {\n"
        "    if (pduel_ != nullptr) {\n"
        "      std::unique_lock<std::shared_timed_mutex> ulock(duel_mtx);\n"
        "      YGO_EndDuel(pduel_);\n"
        "      duel_started_ = false;\n"
        "    }\n"
        "    if (fp_ != nullptr) {\n"
        "      fclose(fp_);\n"
        "      fp_ = nullptr;\n"
        "      is_recording = false;\n"
        "    }\n"
        "    for (int i = 0; i < 2; i++) {\n"
        "      delete players_[i];\n"
        "      players_[i] = nullptr;\n"
        "    }\n"
        "  }",
    ),
    (
        "safe forced reset",
        "  void Reset() override {\n"
        "    // clock_t start = clock();",
        "  void Reset() override {\n"
        "    // clock_t start = clock();\n"
        "    if (pduel_ != nullptr) {\n"
        "      std::unique_lock<std::shared_timed_mutex> ulock(duel_mtx);\n"
        "      YGO_EndDuel(pduel_);\n"
        "      duel_started_ = false;\n"
        "    }",
    ),
    (
        "diagnostic observation card ID lookup",
        "    return card_ids_.at(get_card_code(player, loc, seq));",
        "    return c_get_card_id(get_card_code(player, loc, seq));",
    ),
    (
        "diagnostic deck lookups",
        "    main_deck = main_decks_.at(deck);\n"
        "    extra_deck = extra_decks_.at(deck);",
        "    auto main = main_decks_.find(deck);\n"
        "    if (main == main_decks_.end()) {\n"
        "      throw std::runtime_error(\"Main deck not initialized: \" + deck);\n"
        "    }\n"
        "    auto extra = extra_decks_.find(deck);\n"
        "    if (extra == extra_decks_.end()) {\n"
        "      throw std::runtime_error(\"Extra deck not initialized: \" + deck);\n"
        "    }\n"
        "    main_deck = main->second;\n"
        "    extra_deck = extra->second;",
    ),
    (
        "clear closed replay pointer",
        "        fclose(fp_);\n"
        "        is_recording = false;",
        "        fclose(fp_);\n"
        "        fp_ = nullptr;\n"
        "        is_recording = false;",
    ),
    (
        "clear destroyed duel pointer",
        "  void YGO_EndDuel(OCG_Duel pduel) {\n"
        "    OCG_DestroyDuel(pduel);\n"
        "  }",
        "  void YGO_EndDuel(OCG_Duel pduel) {\n"
        "    OCG_DestroyDuel(pduel);\n"
        "    if (pduel_ == pduel) {\n"
        "      pduel_ = nullptr;\n"
        "    }\n"
        "  }",
    ),
)


BLOCK_REPLACEMENTS = (
    (
        "EDOPro API v11 query records",
        "  CardCode get_card_code(PlayerId player, uint8_t loc, uint8_t seq) {",
        "  std::vector<Card> read_cardlist(bool extra = false, bool extra8 = false) {",
        MODERN_QUERY_READER,
    ),
)


def apply_replacements(source: str) -> str:
    patched = source
    for name, old, new in REPLACEMENTS:
        count = patched.count(old)
        if count != 1:
            raise RuntimeError(
                f"Adapter transform '{name}' expected one match, found {count}"
            )
        patched = patched.replace(old, new, 1)
    for name, start, end, new in BLOCK_REPLACEMENTS:
        if patched.count(start) != 1 or patched.count(end) != 1:
            raise RuntimeError(
                f"Adapter block transform '{name}' requires unique markers"
            )
        start_index = patched.index(start)
        end_index = patched.index(end, start_index)
        patched = patched[:start_index] + new + "\n\n" + patched[end_index:]
    return patched


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_path = args.source.resolve()
    output_path = args.output.resolve()
    if source_path == output_path:
        raise ValueError("Source and output paths must differ")
    source = source_path.read_text(encoding="utf-8")
    patched = apply_replacements(source)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(patched, encoding="utf-8")
    transform_count = len(REPLACEMENTS) + len(BLOCK_REPLACEMENTS)
    print(f"Applied {transform_count} adapter transforms to {output_path}")


if __name__ == "__main__":
    main()
