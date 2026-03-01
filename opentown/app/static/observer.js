(() => {
  const state = {
    tick: 0,
    agents: [],
    hall_chat_tail: [],
    hallChatHistory: [],
    chatMode: "hall",
    selectedPrivateThreadKey: null,
    hallChatFilterChannel: "all",
    hallChatFilterSender: "all",
    hallChatFilterKeyword: "",
    hallChatAutoScroll: true,
    spriteByAgentId: new Map(),
    worldObjects: [],
    objectById: new Map(),
    objectOccupancyById: new Map(),
    showObjectDebug: false,
    objectFilter: "all",
    selectedObjectId: null,
  };

  const tileSize = 32;

  const config = {
    type: Phaser.AUTO,
    width: window.innerWidth - 360,
    height: window.innerHeight,
    parent: "game-container",
    pixelArt: true,
    physics: { default: "arcade", arcade: { gravity: { y: 0 } } },
    scene: { preload, create, update },
  };

  const game = new Phaser.Game(config);
  let mapObj;
  let sceneRef;
  let cameraRef;
  let focusedAgentId = null;
  let autoFocusDone = false;
  let isDragging = false;
  let dragStartPointer = null;
  let dragStartScroll = null;
  let objectMarkersGraphics = null;
  let hallChatPollTimer = null;

  function agentKey(id) {
    return String(id);
  }

  function setCameraCenterWorld(x, y) {
    if (!cameraRef || !mapObj) return;
    const halfW = (cameraRef.width / cameraRef.zoom) / 2;
    const halfH = (cameraRef.height / cameraRef.zoom) / 2;
    const maxScrollX = Math.max(0, mapObj.widthInPixels - (cameraRef.width / cameraRef.zoom));
    const maxScrollY = Math.max(0, mapObj.heightInPixels - (cameraRef.height / cameraRef.zoom));
    cameraRef.scrollX = Phaser.Math.Clamp(x - halfW, 0, maxScrollX);
    cameraRef.scrollY = Phaser.Math.Clamp(y - halfH, 0, maxScrollY);
  }

  function preload() {
    this.load.image("blocks_1", "/assets/assets/the_ville/visuals/map_assets/blocks/blocks_1.png");
    this.load.image("walls", "/assets/assets/the_ville/visuals/map_assets/v1/Room_Builder_32x32.png");
    this.load.image("interiors_pt1", "/assets/assets/the_ville/visuals/map_assets/v1/interiors_pt1.png");
    this.load.image("interiors_pt2", "/assets/assets/the_ville/visuals/map_assets/v1/interiors_pt2.png");
    this.load.image("interiors_pt3", "/assets/assets/the_ville/visuals/map_assets/v1/interiors_pt3.png");
    this.load.image("interiors_pt4", "/assets/assets/the_ville/visuals/map_assets/v1/interiors_pt4.png");
    this.load.image("interiors_pt5", "/assets/assets/the_ville/visuals/map_assets/v1/interiors_pt5.png");
    this.load.image("CuteRPG_Field_B", "/assets/assets/the_ville/visuals/map_assets/cute_rpg_word_VXAce/tilesets/CuteRPG_Field_B.png");
    this.load.image("CuteRPG_Field_C", "/assets/assets/the_ville/visuals/map_assets/cute_rpg_word_VXAce/tilesets/CuteRPG_Field_C.png");
    this.load.image("CuteRPG_Harbor_C", "/assets/assets/the_ville/visuals/map_assets/cute_rpg_word_VXAce/tilesets/CuteRPG_Harbor_C.png");
    this.load.image("CuteRPG_Village_B", "/assets/assets/the_ville/visuals/map_assets/cute_rpg_word_VXAce/tilesets/CuteRPG_Village_B.png");
    this.load.image("CuteRPG_Forest_B", "/assets/assets/the_ville/visuals/map_assets/cute_rpg_word_VXAce/tilesets/CuteRPG_Forest_B.png");
    this.load.image("CuteRPG_Desert_C", "/assets/assets/the_ville/visuals/map_assets/cute_rpg_word_VXAce/tilesets/CuteRPG_Desert_C.png");
    this.load.image("CuteRPG_Mountains_B", "/assets/assets/the_ville/visuals/map_assets/cute_rpg_word_VXAce/tilesets/CuteRPG_Mountains_B.png");
    this.load.image("CuteRPG_Desert_B", "/assets/assets/the_ville/visuals/map_assets/cute_rpg_word_VXAce/tilesets/CuteRPG_Desert_B.png");
    this.load.image("CuteRPG_Forest_C", "/assets/assets/the_ville/visuals/map_assets/cute_rpg_word_VXAce/tilesets/CuteRPG_Forest_C.png");

    this.load.tilemapTiledJSON("map", "/assets/assets/the_ville/visuals/the_ville_jan7.json");
    this.load.atlas("atlas", "/assets/assets/characters/Yuriko_Yamamoto.png", "/assets/assets/characters/atlas.json");
  }

  function colorByObjectType(type) {
    const key = String(type || "").toLowerCase();
    const table = {
      bed: 0x4f46e5,
      seat: 0x0ea5e9,
      toilet: 0x64748b,
      shower: 0x0891b2,
      sink: 0x0284c7,
      kitchen: 0xf59e0b,
      computer: 0x8b5cf6,
      reading: 0x16a34a,
      music: 0xef4444,
      game: 0xdc2626,
      work_surface: 0x7c3aed,
      scene_object: 0x94a3b8,
    };
    return table[key] || 0x64748b;
  }

  function create() {
    sceneRef = this;
    mapObj = this.make.tilemap({ key: "map" });

    const collisions = mapObj.addTilesetImage("blocks", "blocks_1");
    const walls = mapObj.addTilesetImage("Room_Builder_32x32", "walls");
    const interiors_pt1 = mapObj.addTilesetImage("interiors_pt1", "interiors_pt1");
    const interiors_pt2 = mapObj.addTilesetImage("interiors_pt2", "interiors_pt2");
    const interiors_pt3 = mapObj.addTilesetImage("interiors_pt3", "interiors_pt3");
    const interiors_pt4 = mapObj.addTilesetImage("interiors_pt4", "interiors_pt4");
    const interiors_pt5 = mapObj.addTilesetImage("interiors_pt5", "interiors_pt5");
    const CuteRPG_Field_B = mapObj.addTilesetImage("CuteRPG_Field_B", "CuteRPG_Field_B");
    const CuteRPG_Field_C = mapObj.addTilesetImage("CuteRPG_Field_C", "CuteRPG_Field_C");
    const CuteRPG_Harbor_C = mapObj.addTilesetImage("CuteRPG_Harbor_C", "CuteRPG_Harbor_C");
    const CuteRPG_Village_B = mapObj.addTilesetImage("CuteRPG_Village_B", "CuteRPG_Village_B");
    const CuteRPG_Forest_B = mapObj.addTilesetImage("CuteRPG_Forest_B", "CuteRPG_Forest_B");
    const CuteRPG_Desert_C = mapObj.addTilesetImage("CuteRPG_Desert_C", "CuteRPG_Desert_C");
    const CuteRPG_Mountains_B = mapObj.addTilesetImage("CuteRPG_Mountains_B", "CuteRPG_Mountains_B");
    const CuteRPG_Desert_B = mapObj.addTilesetImage("CuteRPG_Desert_B", "CuteRPG_Desert_B");
    const CuteRPG_Forest_C = mapObj.addTilesetImage("CuteRPG_Forest_C", "CuteRPG_Forest_C");

    const group1 = [CuteRPG_Field_B, CuteRPG_Field_C, CuteRPG_Harbor_C, CuteRPG_Village_B,
      CuteRPG_Forest_B, CuteRPG_Desert_C, CuteRPG_Mountains_B, CuteRPG_Desert_B, CuteRPG_Forest_C,
      interiors_pt1, interiors_pt2, interiors_pt3, interiors_pt4, interiors_pt5, walls];

    mapObj.createLayer("Bottom Ground", group1, 0, 0);
    mapObj.createLayer("Exterior Ground", group1, 0, 0);
    mapObj.createLayer("Exterior Decoration L1", group1, 0, 0);
    mapObj.createLayer("Exterior Decoration L2", group1, 0, 0);
    mapObj.createLayer("Interior Ground", group1, 0, 0);
    mapObj.createLayer("Wall", [CuteRPG_Field_C, walls], 0, 0);
    mapObj.createLayer("Interior Furniture L1", group1, 0, 0);
    mapObj.createLayer("Interior Furniture L2 ", group1, 0, 0);
    const fg1 = mapObj.createLayer("Foreground L1", group1, 0, 0);
    const fg2 = mapObj.createLayer("Foreground L2", group1, 0, 0);
    const collisionsLayer = mapObj.createLayer("Collisions", collisions, 0, 0);
    collisionsLayer.setDepth(-1);
    fg1.setDepth(2);
    fg2.setDepth(2);

    cameraRef = this.cameras.main;
    cameraRef.setBounds(0, 0, mapObj.widthInPixels, mapObj.heightInPixels);
    setupCameraDrag(this);
    setupCameraZoom(this);
    setupHallChatModal();
    objectMarkersGraphics = this.add.graphics().setDepth(8);
    setupObjectDebugControls();
    fetchWorldObjects();

    connectWorldWS();
  }

  function setupCameraDrag(scene) {
    scene.input.on("pointerdown", pointer => {
      isDragging = true;
      dragStartPointer = { x: pointer.x, y: pointer.y };
      dragStartScroll = { x: cameraRef.scrollX, y: cameraRef.scrollY };
      state.selectedObjectId = null;
      if (focusedAgentId !== null) {
        focusedAgentId = null;
        cameraRef.stopFollow();
      }
    });

    scene.input.on("pointermove", pointer => {
      if (!isDragging || !dragStartPointer || !dragStartScroll) return;
      const dx = pointer.x - dragStartPointer.x;
      const dy = pointer.y - dragStartPointer.y;
      cameraRef.scrollX = dragStartScroll.x - dx;
      cameraRef.scrollY = dragStartScroll.y - dy;
    });

    const stopDrag = () => {
      isDragging = false;
      dragStartPointer = null;
      dragStartScroll = null;
    };
    scene.input.on("pointerup", stopDrag);
    scene.input.on("pointerupoutside", stopDrag);
  }

  function setupCameraZoom(scene) {
    const minZoom = 0.4;
    const maxZoom = 2.6;
    const zoomStep = 0.12;
    cameraRef.setZoom(1);

    scene.input.on("wheel", (pointer, gameObjects, deltaX, deltaY) => {
      if (!cameraRef) return;
      const current = cameraRef.zoom;
      const next = Phaser.Math.Clamp(current + (deltaY > 0 ? -zoomStep : zoomStep), minZoom, maxZoom);
      if (next === current) return;

      // Keep cursor-anchored zoom so users don't lose context on large maps.
      const before = cameraRef.getWorldPoint(pointer.x, pointer.y);
      cameraRef.setZoom(next);
      const after = cameraRef.getWorldPoint(pointer.x, pointer.y);
      cameraRef.scrollX += before.x - after.x;
      cameraRef.scrollY += before.y - after.y;
    });
  }

  function setupObjectDebugControls() {
    const toggle = document.getElementById("toggle-objects");
    const filter = document.getElementById("object-filter");
    if (toggle) {
      toggle.checked = state.showObjectDebug;
      toggle.onchange = () => {
        state.showObjectDebug = !!toggle.checked;
      };
    }
    if (filter) {
      filter.value = state.objectFilter;
      filter.onchange = () => {
        state.objectFilter = filter.value || "all";
      };
    }
  }

  function isHallChatModalOpen() {
    const modal = document.getElementById("hall-chat-modal");
    return !!modal && !modal.classList.contains("hidden");
  }

  function getHallChatOldestId() {
    let oldest = null;
    for (const m of state.hallChatHistory) {
      if (typeof m.id !== "number") continue;
      if (oldest === null || m.id < oldest) oldest = m.id;
    }
    return oldest;
  }

  function dedupeAndSortHallHistory(rows) {
    const merged = [...state.hallChatHistory, ...rows];
    const byKey = new Map();
    for (const msg of merged) {
      const key = msg.id != null
        ? `id:${msg.id}`
        : `t:${msg.tick}|c:${msg.channel || "hall"}|s:${msg.sender_agent_id || msg.sender_name}|tg:${msg.target_agent_id || "-"}|x:${msg.text}`;
      byKey.set(key, msg);
    }
    state.hallChatHistory = Array.from(byKey.values()).sort((a, b) => {
      if (a.id != null && b.id != null) return a.id - b.id;
      if (a.tick !== b.tick) return a.tick - b.tick;
      return (a.created_at || "").localeCompare(b.created_at || "");
    });
    if (state.hallChatHistory.length > 2000) {
      state.hallChatHistory = state.hallChatHistory.slice(-2000);
    }
  }

  function syncHallChatFilterSenderOptions() {
    const select = document.getElementById("hall-chat-filter-sender");
    if (!select) return;
    const current = state.hallChatFilterSender || "all";
    const names = [...new Set(state.hallChatHistory.map(m => m.sender_name).filter(Boolean))].sort();
    select.innerHTML = "";
    const allOpt = document.createElement("option");
    allOpt.value = "all";
    allOpt.textContent = "全部发言人";
    select.appendChild(allOpt);
    for (const name of names) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    }
    if ([...select.options].some(o => o.value === current)) {
      select.value = current;
    } else {
      select.value = "all";
      state.hallChatFilterSender = "all";
    }
  }

  function hashColor(input) {
    const text = String(input || "agent");
    let hash = 0;
    for (let i = 0; i < text.length; i += 1) {
      hash = ((hash << 5) - hash + text.charCodeAt(i)) | 0;
    }
    const hue = Math.abs(hash) % 360;
    return `hsl(${hue} 62% 46%)`;
  }

  function agentById(agentId) {
    const key = agentKey(agentId);
    return state.agents.find(a => agentKey(a.agent_id) === key) || null;
  }

  function agentLocationText(agentId) {
    const agent = agentById(agentId);
    if (!agent) return "离线";
    return `(${agent.x},${agent.y})`;
  }

  function createAvatar(name, agentId) {
    const avatar = document.createElement("div");
    avatar.className = "chat-avatar";
    avatar.style.background = hashColor(`${name || ""}-${agentId || ""}`);
    const label = String(name || "A").trim();
    avatar.textContent = (label[0] || "A").toUpperCase();
    return avatar;
  }

  function setChatMode(mode) {
    state.chatMode = mode === "private" ? "private" : "hall";
    state.hallChatFilterChannel = state.chatMode === "private" ? "local" : "hall";
    const hallBtn = document.getElementById("chat-mode-hall");
    const privateBtn = document.getElementById("chat-mode-private");
    if (hallBtn) hallBtn.classList.toggle("active", state.chatMode === "hall");
    if (privateBtn) privateBtn.classList.toggle("active", state.chatMode === "private");
  }

  function filteredHallRows() {
    let rows = [...state.hallChatHistory];
    if (state.hallChatFilterChannel && state.hallChatFilterChannel !== "all") {
      rows = rows.filter(m => m.channel === state.hallChatFilterChannel);
    }
    if (state.hallChatFilterSender && state.hallChatFilterSender !== "all") {
      rows = rows.filter(m => m.sender_name === state.hallChatFilterSender);
    }
    const kw = (state.hallChatFilterKeyword || "").trim().toLowerCase();
    if (kw) {
      rows = rows.filter(m => String(m.text || "").toLowerCase().includes(kw));
    }
    return rows;
  }

  function setupHallChatModal() {
    const openBtn = document.getElementById("open-hall-chat-modal");
    const closeBtn = document.getElementById("close-hall-chat-modal");
    const refreshBtn = document.getElementById("refresh-hall-chat-modal");
    const loadMoreBtn = document.getElementById("load-more-hall-chat-modal");
    const hallModeBtn = document.getElementById("chat-mode-hall");
    const privateModeBtn = document.getElementById("chat-mode-private");
    const senderFilter = document.getElementById("hall-chat-filter-sender");
    const keywordFilter = document.getElementById("hall-chat-filter-keyword");
    const autoScroll = document.getElementById("hall-chat-auto-scroll");
    const modal = document.getElementById("hall-chat-modal");

    if (openBtn) {
      openBtn.onclick = () => {
        openHallChatModal();
      };
    }
    if (closeBtn) {
      closeBtn.onclick = () => {
        closeHallChatModal();
      };
    }
    if (refreshBtn) {
      refreshBtn.onclick = () => {
        refreshHallChatModalHistory({ mode: "latest" });
      };
    }
    if (loadMoreBtn) {
      loadMoreBtn.onclick = () => {
        refreshHallChatModalHistory({ mode: "older" });
      };
    }
    if (hallModeBtn) {
      hallModeBtn.onclick = () => {
        setChatMode("hall");
        renderHallChatModal();
      };
    }
    if (privateModeBtn) {
      privateModeBtn.onclick = () => {
        setChatMode("private");
        renderHallChatModal();
      };
    }
    if (senderFilter) {
      senderFilter.onchange = () => {
        state.hallChatFilterSender = senderFilter.value || "all";
        renderHallChatModal();
      };
    }
    if (keywordFilter) {
      keywordFilter.oninput = () => {
        state.hallChatFilterKeyword = keywordFilter.value || "";
        renderHallChatModal();
      };
    }
    if (autoScroll) {
      autoScroll.checked = state.hallChatAutoScroll;
      autoScroll.onchange = () => {
        state.hallChatAutoScroll = !!autoScroll.checked;
      };
    }
    if (modal) {
      modal.addEventListener("click", evt => {
        if (evt.target === modal) {
          closeHallChatModal();
        }
      });
    }
    document.addEventListener("keydown", evt => {
      if (evt.key === "Escape" && isHallChatModalOpen()) {
        closeHallChatModal();
      }
    });
    setChatMode(state.chatMode);
  }

  function openHallChatModal() {
    const modal = document.getElementById("hall-chat-modal");
    if (!modal) return;
    setChatMode("hall");
    modal.classList.remove("hidden");
    document.body.classList.add("modal-open");
    refreshHallChatModalHistory({ mode: "latest" });
    if (hallChatPollTimer) clearInterval(hallChatPollTimer);
    hallChatPollTimer = setInterval(() => {
      refreshHallChatModalHistory({ mode: "latest", silent: true });
    }, 5000);
  }

  function closeHallChatModal() {
    const modal = document.getElementById("hall-chat-modal");
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.classList.remove("modal-open");
    if (hallChatPollTimer) {
      clearInterval(hallChatPollTimer);
      hallChatPollTimer = null;
    }
  }

  function mergeTailIntoHallHistory() {
    if (!state.hall_chat_tail || state.hall_chat_tail.length === 0) return;
    const appended = [];
    for (const msg of state.hall_chat_tail) {
      appended.push({
        id: null,
        tick: msg.tick,
        channel: msg.channel || "hall",
        sender_agent_id: msg.sender_agent_id,
        sender_name: msg.sender_name,
        target_agent_id: msg.target_agent_id || null,
        target_name: msg.target_name || null,
        text: msg.text,
        created_at: null,
      });
    }
    dedupeAndSortHallHistory(appended);
  }

  function mockChatRows() {
    const baseTick = Math.max(1, state.tick || 1);
    return [
      {
        id: -6,
        tick: baseTick - 14,
        channel: "hall",
        sender_agent_id: 1001,
        sender_name: "Townie_Ava",
        target_agent_id: null,
        target_name: null,
        text: "大家早上好，今天广场见，分享一下昨晚的探索路线。",
        created_at: null,
      },
      {
        id: -5,
        tick: baseTick - 12,
        channel: "hall",
        sender_agent_id: 1002,
        sender_name: "Townie_Leo",
        target_agent_id: null,
        target_name: null,
        text: "我在图书角附近发现了新的可交互对象，稍后整理给大家。",
        created_at: null,
      },
      {
        id: -4,
        tick: baseTick - 10,
        channel: "local",
        sender_agent_id: 1001,
        sender_name: "Townie_Ava",
        target_agent_id: 1003,
        target_name: "Townie_Mia",
        text: "你现在离我很近，要不要一起去厨房做饭？",
        created_at: null,
      },
      {
        id: -3,
        tick: baseTick - 9,
        channel: "local",
        sender_agent_id: 1003,
        sender_name: "Townie_Mia",
        target_agent_id: 1001,
        target_name: "Townie_Ava",
        text: "可以，3 个 tick 后在餐桌集合。",
        created_at: null,
      },
      {
        id: -2,
        tick: baseTick - 6,
        channel: "hall",
        sender_agent_id: 1004,
        sender_name: "Townie_Noah",
        target_agent_id: null,
        target_name: null,
        text: "提醒：广场聊天是全体可见，私聊用于近距离双人协商。",
        created_at: null,
      },
      {
        id: -1,
        tick: baseTick - 3,
        channel: "local",
        sender_agent_id: 1002,
        sender_name: "Townie_Leo",
        target_agent_id: 1004,
        target_name: "Townie_Noah",
        text: "我在你附近，先私聊确认任务分工。",
        created_at: null,
      },
    ];
  }

  async function refreshHallChatModalHistory(opts = {}) {
    const mode = opts.mode || "latest";
    const silent = !!opts.silent;
    const status = document.getElementById("hall-chat-modal-status");
    try {
      if (!silent && status) status.textContent = "加载大厅聊天中...";
      let url = "/api/chat/history?limit=500";
      if (mode === "older") {
        const oldest = getHallChatOldestId();
        if (oldest != null) {
          url += `&before_id=${oldest}`;
        } else {
          url = "/api/chat/history?limit=500";
        }
      }
      const res = await fetch(url);
      const data = await res.json();
      if (Array.isArray(data.rows)) {
        if (mode === "older") {
          dedupeAndSortHallHistory(data.rows);
        } else {
          state.hallChatHistory = data.rows;
        }
      }
      mergeTailIntoHallHistory();
      if (state.hallChatHistory.length === 0) {
        dedupeAndSortHallHistory(mockChatRows());
      }
      syncHallChatFilterSenderOptions();
      if (status) {
        status.textContent = `共 ${state.hallChatHistory.length} 条大厅聊天记录`;
      }
      renderHallChatModal();
    } catch (e) {
      if (status) {
        status.textContent = "大厅聊天加载失败";
      }
      renderHallChatModal();
    }
  }

  function renderHallChatModal() {
    const speakersBox = document.getElementById("hall-chat-modal-speakers");
    const list = document.getElementById("hall-chat-modal-list");
    const status = document.getElementById("hall-chat-modal-status");
    if (!list || !speakersBox) return;
    const previousScrollBottomOffset = list.scrollHeight - list.scrollTop;
    list.innerHTML = "";
    speakersBox.innerHTML = "";
    const rows = filteredHallRows().slice(-1000);
    if (state.chatMode === "private") {
      renderPrivateThreadLayout(speakersBox, list, rows.filter(r => r.channel === "local"));
    } else {
      renderHallGroupLayout(speakersBox, list, rows.filter(r => r.channel === "hall"));
    }

    if (status) {
      const hallCount = state.hallChatHistory.filter(r => r.channel === "hall").length;
      const localCount = state.hallChatHistory.filter(r => r.channel === "local").length;
      status.textContent = state.chatMode === "hall"
        ? `广场群聊 ${hallCount} 条 | 私聊 ${localCount} 条`
        : `私聊会话 ${localCount} 条 | 广场群聊 ${hallCount} 条`;
    }

    if (state.hallChatAutoScroll) {
      list.scrollTop = list.scrollHeight;
    } else {
      list.scrollTop = Math.max(0, list.scrollHeight - previousScrollBottomOffset);
    }
  }

  function renderHallGroupLayout(sidebar, list, rows) {
    const title = document.createElement("div");
    title.className = "dm-title";
    title.textContent = `在线居民 (${state.agents.length})`;
    sidebar.appendChild(title);

    const sortedAgents = [...state.agents].sort((a, b) => String(a.public_name).localeCompare(String(b.public_name)));
    for (const agent of sortedAgents) {
      const item = document.createElement("div");
      item.className = `speaker-item${focusedAgentId === agentKey(agent.agent_id) ? " active" : ""}`;
      item.onclick = () => focusAgent(agent.agent_id);
      const mini = document.createElement("div");
      mini.className = "agent-mini";
      mini.appendChild(createAvatar(agent.public_name, agent.agent_id));
      const meta = document.createElement("div");
      meta.className = "agent-mini-meta";
      const name = document.createElement("div");
      name.className = "agent-mini-name";
      name.textContent = agent.public_name;
      const loc = document.createElement("div");
      loc.className = "agent-mini-loc";
      loc.textContent = `${agent.state} @ (${agent.x},${agent.y})`;
      meta.appendChild(name);
      meta.appendChild(loc);
      mini.appendChild(meta);
      item.appendChild(mini);
      sidebar.appendChild(item);
    }

    if (rows.length === 0) {
      const empty = document.createElement("div");
      empty.className = "chat-empty";
      empty.textContent = "暂无广场聊天消息";
      list.appendChild(empty);
      return;
    }

    for (const msg of rows) {
      const item = document.createElement("div");
      item.className = "group-line";
      const row = document.createElement("div");
      row.className = "chat-msg-row";

      const agentCol = document.createElement("div");
      agentCol.className = "chat-agent-col";
      agentCol.appendChild(createAvatar(msg.sender_name, msg.sender_agent_id));
      const name = document.createElement("div");
      name.className = "chat-agent-name";
      name.textContent = msg.sender_name || "未知居民";
      const loc = document.createElement("div");
      loc.className = "chat-agent-loc";
      loc.textContent = agentLocationText(msg.sender_agent_id);
      agentCol.appendChild(name);
      agentCol.appendChild(loc);

      const contentBox = document.createElement("div");
      const meta = document.createElement("div");
      meta.className = "group-meta";
      const when = msg.created_at ? new Date(msg.created_at).toLocaleString() : "";
      meta.innerHTML = `<span class="chat-chip hall">广场群聊</span>Tick ${msg.tick}${when ? ` · ${when}` : ""}`;
      const text = document.createElement("div");
      text.className = "group-text";
      text.textContent = msg.text || "";
      contentBox.appendChild(meta);
      contentBox.appendChild(text);

      row.appendChild(agentCol);
      row.appendChild(contentBox);
      item.appendChild(row);
      list.appendChild(item);
    }
  }

  function buildPrivateThreads(rows) {
    const threadMap = new Map();
    for (const msg of rows) {
      const senderId = msg.sender_agent_id ?? `name:${msg.sender_name}`;
      const targetId = msg.target_agent_id;
      let key = `near:${String(senderId)}`;
      if (targetId != null) {
        const pair = [String(senderId), String(targetId)].sort();
        key = `pair:${pair[0]}:${pair[1]}`;
      }

      let thread = threadMap.get(key);
      if (!thread) {
        thread = {
          key,
          messages: [],
          participants: new Map(),
          lastTick: -1,
          lastText: "",
        };
        threadMap.set(key, thread);
      }

      thread.messages.push(msg);
      thread.lastTick = Math.max(thread.lastTick, Number(msg.tick || 0));
      thread.lastText = msg.text || "";
      thread.participants.set(`s:${msg.sender_agent_id ?? msg.sender_name}`, {
        agent_id: msg.sender_agent_id ?? null,
        name: msg.sender_name || "未知居民",
      });
      if (msg.target_agent_id != null || msg.target_name) {
        thread.participants.set(`t:${msg.target_agent_id ?? msg.target_name}`, {
          agent_id: msg.target_agent_id ?? null,
          name: msg.target_name || `agent_${msg.target_agent_id}`,
        });
      }
    }

    return Array.from(threadMap.values())
      .map(thread => {
        const participants = Array.from(thread.participants.values()).sort((a, b) => String(a.name).localeCompare(String(b.name)));
        const titled = participants.slice(0, 2).map(p => p.name);
        const title = titled.length >= 2 ? `${titled[0]} ↔ ${titled[1]}` : `${titled[0] || "附近会话"}`;
        const rightAgentId = participants.length >= 2 ? participants[1].agent_id : null;
        return {
          ...thread,
          participants,
          title,
          rightAgentId: rightAgentId == null ? null : agentKey(rightAgentId),
        };
      })
      .sort((a, b) => b.lastTick - a.lastTick);
  }

  function renderPrivateThreadLayout(sidebar, list, rows) {
    const threads = buildPrivateThreads(rows);
    const title = document.createElement("div");
    title.className = "dm-title";
    title.textContent = `私聊会话 (${threads.length})`;
    sidebar.appendChild(title);

    if (threads.length === 0) {
      const emptySide = document.createElement("div");
      emptySide.className = "chat-empty";
      emptySide.textContent = "暂无私聊会话";
      sidebar.appendChild(emptySide);

      const emptyMain = document.createElement("div");
      emptyMain.className = "chat-empty";
      emptyMain.textContent = "还没有私聊记录";
      list.appendChild(emptyMain);
      return;
    }

    if (!threads.some(t => t.key === state.selectedPrivateThreadKey)) {
      state.selectedPrivateThreadKey = threads[0].key;
    }

    for (const thread of threads) {
      const item = document.createElement("div");
      item.className = `speaker-item${thread.key === state.selectedPrivateThreadKey ? " active" : ""}`;
      item.onclick = () => {
        state.selectedPrivateThreadKey = thread.key;
        renderHallChatModal();
      };

      const head = document.createElement("div");
      head.className = "agent-mini";
      const avatarTarget = thread.participants[0] || { name: "会话" };
      head.appendChild(createAvatar(avatarTarget.name, avatarTarget.agent_id));
      const meta = document.createElement("div");
      meta.className = "agent-mini-meta";
      const name = document.createElement("div");
      name.className = "agent-mini-name";
      name.textContent = thread.title;
      const desc = document.createElement("div");
      desc.className = "dm-thread-last";
      desc.textContent = `Tick ${thread.lastTick} · ${thread.lastText}`;
      meta.appendChild(name);
      meta.appendChild(desc);
      head.appendChild(meta);
      item.appendChild(head);
      sidebar.appendChild(item);
    }

    const active = threads.find(t => t.key === state.selectedPrivateThreadKey) || threads[0];
    const convHead = document.createElement("div");
    convHead.className = "dm-conv-head";
    const first = active.participants[0];
    if (first) convHead.appendChild(createAvatar(first.name, first.agent_id));
    const second = active.participants[1];
    if (second) convHead.appendChild(createAvatar(second.name, second.agent_id));
    const convMeta = document.createElement("div");
    const convTitle = document.createElement("div");
    convTitle.className = "dm-conv-title";
    convTitle.textContent = active.title;
    const convLoc = document.createElement("div");
    convLoc.className = "dm-conv-meta";
    const locations = active.participants
      .map(p => `${p.name}: ${agentLocationText(p.agent_id)}`)
      .join(" | ");
    convLoc.textContent = locations || "位置未知";
    convMeta.appendChild(convTitle);
    convMeta.appendChild(convLoc);
    convHead.appendChild(convMeta);
    list.appendChild(convHead);

    for (const msg of active.messages) {
      const bubbleWrap = document.createElement("div");
      const isRight = active.rightAgentId != null && agentKey(msg.sender_agent_id) === active.rightAgentId;
      bubbleWrap.className = `dm-bubble-wrap${isRight ? " right" : ""}`;

      const bubble = document.createElement("div");
      bubble.className = "dm-bubble";
      const meta = document.createElement("div");
      meta.className = "dm-bubble-meta";
      const when = msg.created_at ? new Date(msg.created_at).toLocaleString() : "";
      meta.textContent = `${msg.sender_name || "未知居民"} · ${agentLocationText(msg.sender_agent_id)} · Tick ${msg.tick}${when ? ` · ${when}` : ""}`;
      const text = document.createElement("div");
      text.className = "dm-bubble-text";
      text.textContent = msg.text || "";
      bubble.appendChild(meta);
      bubble.appendChild(text);
      bubbleWrap.appendChild(bubble);
      list.appendChild(bubbleWrap);
    }
  }

  async function fetchWorldObjects() {
    try {
      const res = await fetch("/api/world/objects?limit=5000");
      const data = await res.json();
      state.worldObjects = (data.rows || []).map(row => ({
        ...row,
        affordances: row.affordances || [],
      }));
      state.objectById = new Map(state.worldObjects.map(o => [o.object_id, o]));
      const stats = document.getElementById("object-stats");
      if (stats) {
        stats.textContent = `已加载 ${state.worldObjects.length} 个对象`;
      }
    } catch (e) {
      const stats = document.getElementById("object-stats");
      if (stats) {
        stats.textContent = "对象索引加载失败";
      }
    }
  }

  function update() {
    syncSprites();
    rebuildObjectOccupancy();
    drawObjectMarkers();
    renderPanels();
  }

  function ensureSprite(agent) {
    const key = agentKey(agent.agent_id);
    if (state.spriteByAgentId.has(key)) return;
    const x = agent.x * tileSize + tileSize / 2;
    const y = agent.y * tileSize + tileSize;
    const sprite = sceneRef.physics.add.sprite(x, y, "atlas", "down").setSize(30, 40).setOffset(0, 32).setDepth(10);
    const nameText = sceneRef.add.text(x - 12, y - 42, agent.public_name.slice(0, 8), { font: "12px monospace", fill: "#111", backgroundColor: "#ffffff" }).setDepth(11);
    state.spriteByAgentId.set(key, { sprite, nameText });
  }

  function focusAgent(agentId) {
    if (!cameraRef) return;
    const key = agentKey(agentId);
    const holder = state.spriteByAgentId.get(key);
    focusedAgentId = key;
    state.selectedObjectId = null;
    if (!holder) {
      const agent = state.agents.find(a => agentKey(a.agent_id) === key);
      if (agent) {
        const tx = agent.x * tileSize + tileSize / 2;
        const ty = agent.y * tileSize + tileSize;
        setCameraCenterWorld(tx, ty);
      }
      return;
    }
    setCameraCenterWorld(holder.sprite.x, holder.sprite.y);
    cameraRef.startFollow(holder.sprite, true, 0.12, 0.12);
  }

  function jumpToAgent(agent) {
    if (!cameraRef || !agent) return;
    const tx = agent.x * tileSize + tileSize / 2;
    const ty = agent.y * tileSize + tileSize;
    focusedAgentId = agentKey(agent.agent_id);
    state.selectedObjectId = null;
    cameraRef.stopFollow();
    // Force camera jump first, then attach follow.
    setCameraCenterWorld(tx, ty);
    focusAgent(agent.agent_id);
  }

  function focusObject(objectId) {
    if (!cameraRef) return;
    const obj = state.objectById.get(objectId);
    if (!obj) return;
    state.selectedObjectId = objectId;
    focusedAgentId = null;
    cameraRef.stopFollow();
    cameraRef.centerOn(obj.x * tileSize + tileSize / 2, obj.y * tileSize + tileSize / 2);
  }

  function rebuildObjectOccupancy() {
    const map = new Map();
    for (const a of state.agents) {
      if (a.interacting_object_id) {
        map.set(a.interacting_object_id, a);
      }
    }
    state.objectOccupancyById = map;
  }

  function objectPassesFilter(obj) {
    return state.objectFilter === "all" || obj.type === state.objectFilter;
  }

  function drawObjectMarkers() {
    if (!objectMarkersGraphics || !cameraRef) return;
    objectMarkersGraphics.clear();
    if (!state.showObjectDebug) return;
    if (!state.worldObjects || state.worldObjects.length === 0) return;

    const view = cameraRef.worldView;
    const pad = tileSize * 2;
    for (const obj of state.worldObjects) {
      if (!objectPassesFilter(obj)) continue;
      const px = obj.x * tileSize + tileSize / 2;
      const py = obj.y * tileSize + tileSize / 2;
      if (px < view.x - pad || py < view.y - pad || px > view.right + pad || py > view.bottom + pad) {
        continue;
      }

      const occupied = state.objectOccupancyById.has(obj.object_id);
      const color = occupied ? 0xef4444 : colorByObjectType(obj.type);
      const alpha = state.selectedObjectId === obj.object_id ? 0.95 : 0.7;
      const radius = state.selectedObjectId === obj.object_id ? 6 : 4;
      objectMarkersGraphics.fillStyle(color, alpha);
      objectMarkersGraphics.fillCircle(px, py, radius);
    }
  }

  function syncSprites() {
    if (!sceneRef) return;
    const ids = new Set();
    for (const a of state.agents) {
      const key = agentKey(a.agent_id);
      ids.add(key);
      ensureSprite(a);
      const holder = state.spriteByAgentId.get(key);
      if (!holder) continue;
      const tx = a.x * tileSize + tileSize / 2;
      const ty = a.y * tileSize + tileSize;
      holder.sprite.x = Phaser.Math.Linear(holder.sprite.x, tx, 0.35);
      holder.sprite.y = Phaser.Math.Linear(holder.sprite.y, ty, 0.35);
      holder.nameText.x = holder.sprite.x - 14;
      holder.nameText.y = holder.sprite.y - 42;
    }

    if (!autoFocusDone && focusedAgentId === null && state.agents.length > 0) {
      focusAgent(state.agents[0].agent_id);
      autoFocusDone = true;
    } else if (focusedAgentId !== null && !ids.has(focusedAgentId)) {
      focusedAgentId = null;
      if (state.agents.length > 0) {
        focusAgent(state.agents[0].agent_id);
        autoFocusDone = true;
      }
    }

    for (const [key, holder] of state.spriteByAgentId.entries()) {
      if (!ids.has(key)) {
        holder.sprite.destroy();
        holder.nameText.destroy();
        state.spriteByAgentId.delete(key);
      }
    }
  }

  function renderPanels() {
    document.getElementById("tick").textContent = String(state.tick);

    const list = document.getElementById("agent-list");
    list.innerHTML = "";
    for (const a of state.agents) {
      const key = agentKey(a.agent_id);
      const row = document.createElement("div");
      row.className = `agent-row${focusedAgentId === key ? " active" : ""}`;
      const pending = a.pending_interaction_target_id ? ` -> ${a.pending_interaction_target_id}` : "";
      row.innerHTML = `<span>${a.public_name}</span><span>${a.state}${pending} @ (${a.x},${a.y})</span>`;
      row.title = "点击跳转并跟随该居民";
      row.onclick = () => jumpToAgent(a);
      list.appendChild(row);
    }

    const hall = document.getElementById("hall-chat");
    hall.innerHTML = "";
    for (const m of state.hall_chat_tail.slice(-25)) {
      const line = document.createElement("div");
      line.className = "chat-line";
      line.textContent = `[${m.tick}] ${m.sender_name}: ${m.text}`;
      hall.appendChild(line);
    }

    renderHallChatCta();
    renderOnlineSummary();
    renderObjectDebugPanel();
  }

  function renderHallChatCta() {
    const sub = document.getElementById("hall-chat-cta-sub");
    const badge = document.getElementById("hall-chat-cta-badge");
    if (!sub || !badge) return;

    const latestTail = state.hall_chat_tail[state.hall_chat_tail.length - 1];
    const latestHistory = state.hallChatHistory[state.hallChatHistory.length - 1];
    const latest = latestTail || latestHistory || null;
    if (!latest) {
      sub.textContent = "暂时没有聊天消息";
      badge.classList.add("hidden");
      return;
    }

    const sender = latest.sender_name || "居民";
    const text = String(latest.text || "").replace(/\s+/g, " ").trim();
    const preview = text.length > 24 ? `${text.slice(0, 24)}...` : text;
    const channel = latest.channel === "local" ? "私聊" : "广场";
    sub.textContent = `[${channel}] ${sender}: ${preview || "..."}`;

    const tailCount = state.hall_chat_tail.length;
    if (tailCount > 0) {
      badge.classList.remove("hidden");
      badge.textContent = tailCount > 99 ? "99+" : String(tailCount);
    } else {
      badge.classList.add("hidden");
    }
  }

  function renderOnlineSummary() {
    const box = document.getElementById("online-summary");
    if (!box) return;
    const online = state.agents.length;
    const moving = state.agents.filter(a => a.state === "MOVING").length;
    const talking = state.agents.filter(a => a.state === "TALKING").length;
    const interacting = state.agents.filter(a => !!a.interacting_object_id || !!a.pending_interaction_target_id).length;
    box.innerHTML = `在线人数: <strong>${online}</strong><br>移动中: ${moving} | 交互中: ${interacting} | 聊天中: ${talking}`;
  }

  function renderObjectDebugPanel() {
    const stats = document.getElementById("object-stats");
    const box = document.getElementById("object-nearby");
    if (!stats || !box) return;

    if (!state.worldObjects.length) {
      stats.textContent = "对象索引加载中...";
      box.innerHTML = "";
      return;
    }

    const filteredCount = state.worldObjects.filter(objectPassesFilter).length;
    const occupiedCount = state.worldObjects.filter(
      obj => objectPassesFilter(obj) && state.objectOccupancyById.has(obj.object_id),
    ).length;
    stats.textContent = `类型过滤: ${state.objectFilter} | 可见对象: ${filteredCount} | 占用: ${occupiedCount}`;

    let anchor = null;
    if (focusedAgentId !== null) {
      anchor = state.agents.find(a => agentKey(a.agent_id) === focusedAgentId) || null;
    }
    if (!anchor && state.agents.length > 0) {
      anchor = state.agents[0];
    }

    let rows = [];
    if (anchor) {
      rows = state.worldObjects
        .filter(objectPassesFilter)
        .map(obj => {
          const dx = obj.x - anchor.x;
          const dy = obj.y - anchor.y;
          return { obj, dist: Math.hypot(dx, dy) };
        })
        .sort((a, b) => a.dist - b.dist)
        .slice(0, 12);
    } else {
      rows = state.worldObjects.filter(objectPassesFilter).slice(0, 12).map(obj => ({ obj, dist: NaN }));
    }

    box.innerHTML = "";
    for (const item of rows) {
      const obj = item.obj;
      const row = document.createElement("div");
      row.className = "object-row";
      const occupier = state.objectOccupancyById.get(obj.object_id);
      const occText = occupier ? `占用: ${occupier.public_name}` : "空闲";
      const distText = Number.isFinite(item.dist) ? item.dist.toFixed(2) : "--";
      row.innerHTML = `<div><strong>${obj.name}</strong> (${obj.type})</div><div class="muted">id=${obj.object_id}</div><div class="muted">(${obj.x},${obj.y}) | dist=${distText} | ${occText}</div><div class="muted">verbs: ${(obj.affordances || []).join(", ") || "LOOK"}</div>`;
      row.onclick = () => focusObject(obj.object_id);
      box.appendChild(row);
    }
  }

  function connectWorldWS() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${location.host}/ws/world`);

    ws.onopen = () => {
      ws.send("observer");
      setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
      }, 10000);
    };

    ws.onmessage = evt => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === "world_tick") {
          state.tick = msg.data.tick;
          state.agents = msg.data.agents || [];
          state.hall_chat_tail = msg.data.hall_chat_tail || [];
          mergeTailIntoHallHistory();
          if (isHallChatModalOpen()) {
            const status = document.getElementById("hall-chat-modal-status");
            if (status) {
              status.textContent = `共 ${state.hallChatHistory.length} 条大厅聊天记录`;
            }
            renderHallChatModal();
          }
        }
      } catch (e) {
        console.error(e);
      }
    };

    ws.onclose = () => setTimeout(connectWorldWS, 1000);
  }
})();
