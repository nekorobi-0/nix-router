const $ = (selector) => document.querySelector(selector);
let portsLoaded = false;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#039;");
}

function duration(seconds) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return [days && `${days}日`, `${hours}時間`, `${minutes}分`]
    .filter(Boolean)
    .join(" ");
}

function interfaceCard(networkInterface) {
  const addresses = networkInterface.addresses.length
    ? networkInterface.addresses
        .map(
          (item) =>
            `<li><code>${escapeHtml(item.address)}/${escapeHtml(item.prefixLength)}</code><small>${escapeHtml(item.family)} · ${escapeHtml(item.scope)}</small></li>`,
        )
        .join("")
    : "<li class=\"empty\">アドレスなし</li>";

  const state = (networkInterface.state || "UNKNOWN").toLowerCase();
  return `
    <article class="interface-card">
      <div class="interface-heading">
        <h3>${escapeHtml(networkInterface.name)}</h3>
        <span class="state ${escapeHtml(state)}">${escapeHtml(networkInterface.state)}</span>
      </div>
      <dl>
        <div><dt>MAC</dt><dd>${escapeHtml(networkInterface.mac || "—")}</dd></div>
        <div><dt>MTU</dt><dd>${escapeHtml(networkInterface.mtu || "—")}</dd></div>
      </dl>
      <ul>${addresses}</ul>
    </article>`;
}

function bgpPeerCard(peer) {
  const established = peer.state === "Established";
  return `
    <article class="interface-card">
      <div class="interface-heading">
        <h3>${escapeHtml(peer.address)}</h3>
        <span class="state ${established ? "up" : "down"}">${escapeHtml(peer.state)}</span>
      </div>
      <dl>
        <div><dt>REMOTE AS</dt><dd>${escapeHtml(peer.remoteAs ?? "—")}</dd></div>
        <div><dt>UPTIME</dt><dd>${escapeHtml(peer.uptime || "—")}</dd></div>
        <div><dt>RECEIVED PREFIXES</dt><dd>${escapeHtml(peer.prefixesReceived ?? "—")}</dd></div>
      </dl>
    </article>`;
}

function metric(label, value) {
  return `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? "—")}</strong></article>`;
}

function detailRow(label, value) {
  return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value ?? "—")}</dd></div>`;
}

function bgpRouteTable(routes, emptyMessage) {
  if (!routes.length) return `<p class="empty route-empty">${escapeHtml(emptyMessage)}</p>`;

  return `
    <div class="route-table-wrap">
      <table class="route-table">
        <thead>
          <tr>
            <th>Prefix</th>
            <th>AS Path</th>
            <th>Next Hop</th>
            <th>MED</th>
            <th>Local Pref</th>
            <th>Weight</th>
            <th>Origin</th>
            <th>Flags</th>
          </tr>
        </thead>
        <tbody>
          ${routes.map((route) => `
            <tr>
              <td><code>${escapeHtml(route.prefix)}</code></td>
              <td>${escapeHtml(route.asPath || "—")}</td>
              <td>${escapeHtml(route.nextHops?.join(", ") || "—")}</td>
              <td>${escapeHtml(route.metric ?? "—")}</td>
              <td>${escapeHtml(route.localPreference ?? "—")}</td>
              <td>${escapeHtml(route.weight ?? "—")}</td>
              <td>${escapeHtml(route.origin || "—")}</td>
              <td>
                ${route.bestPath ? '<span class="route-flag best">BEST</span>' : ""}
                ${route.valid ? '<span class="route-flag">VALID</span>' : ""}
              </td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
}

function bgpPeerDetails(peer) {
  const established = peer.state === "Established";
  const receivedRoutes = peer.receivedRoutes || [];
  const advertisedRoutes = peer.advertisedRoutes || [];
  return `
    <article class="peer-detail">
      <div class="interface-heading">
        <div>
          <p class="eyebrow">BGP PEER</p>
          <h3>${escapeHtml(peer.address)}</h3>
        </div>
        <span class="state ${established ? "up" : "down"}">${escapeHtml(peer.state)}</span>
      </div>
      <div class="detail-columns">
        <dl>
          ${detailRow("REMOTE AS", peer.remoteAs)}
          ${detailRow("LOCAL AS", peer.localAs)}
          ${detailRow("UPTIME", peer.uptime)}
          ${detailRow("PEER STATE", peer.peerState)}
          ${detailRow("SOFTWARE", peer.softwareVersion)}
        </dl>
        <dl>
          ${detailRow("PREFIXES RECEIVED", peer.prefixesReceived)}
          ${detailRow("PREFIXES SENT", peer.prefixesSent)}
          ${detailRow("MESSAGES RECEIVED", peer.messagesReceived)}
          ${detailRow("MESSAGES SENT", peer.messagesSent)}
        </dl>
        <dl>
          ${detailRow("INPUT QUEUE", peer.inputQueue)}
          ${detailRow("OUTPUT QUEUE", peer.outputQueue)}
          ${detailRow("CONNECTIONS", peer.connectionsEstablished)}
          ${detailRow("DROPPED", peer.connectionsDropped)}
        </dl>
      </div>
      <div class="route-section">
        <div class="section-title">
          <h4>Received routes</h4>
          <span class="muted">${escapeHtml(receivedRoutes.length)} prefixes</span>
        </div>
        ${bgpRouteTable(receivedRoutes, "このピアから採用している経路はありません。")}
      </div>
      <div class="route-section">
        <div class="section-title">
          <h4>Advertised routes</h4>
          <span class="muted">${escapeHtml(advertisedRoutes.length)} prefixes</span>
        </div>
        ${bgpRouteTable(advertisedRoutes, "このピアへ広告している経路はありません。")}
      </div>
    </article>`;
}

function renderBgp(bgp) {
  if (!bgp?.available) {
    $("#bgp-summary").textContent = "取得不可";
    $("#bgp").innerHTML = "<p class=\"empty\">FRRからBGPステータスを取得できません。</p>";
    $("#bgp-detail-heading").textContent = "FRRからBGPステータスを取得できません。";
    $("#bgp-stats").innerHTML = "";
    $("#bgp-details").innerHTML = "";
    return;
  }

  $("#bgp-summary").textContent =
    `Router ID ${bgp.routerId || "—"} · AS${bgp.localAs ?? "—"} · ${bgp.peers.length} peer`;
  $("#bgp").innerHTML = bgp.peers.length
    ? bgp.peers.map(bgpPeerCard).join("")
    : "<p class=\"empty\">BGPピアが設定されていません。</p>";

  $("#bgp-detail-heading").textContent =
    `Router ID ${bgp.routerId || "—"} · AS${bgp.localAs ?? "—"} · VRF ${bgp.vrfName || "default"}`;
  $("#bgp-stats").innerHTML = [
    metric("ROUTES", bgp.routeCount),
    metric("PEERS", bgp.peerCount ?? bgp.peers.length),
    metric("FAILED PEERS", bgp.failedPeers),
    metric("TABLE VERSION", bgp.tableVersion),
  ].join("");
  $("#bgp-details").innerHTML = bgp.peers.length
    ? bgp.peers.map(bgpPeerDetails).join("")
    : "<p class=\"empty\">BGPピアが設定されていません。</p>";
}

function portRule(rule = {}) {
  const protocol = rule.protocol || "tcp";
  return `
    <article class="port-rule">
      <label>
        <span>Protocol</span>
        <select data-field="protocol">
          <option value="tcp"${protocol === "tcp" ? " selected" : ""}>TCP</option>
          <option value="udp"${protocol === "udp" ? " selected" : ""}>UDP</option>
        </select>
      </label>
      <label>
        <span>公開ポート</span>
        <input data-field="external_port" type="number" min="1" max="65535" required value="${escapeHtml(rule.external_port ?? "")}">
      </label>
      <label class="target-host">
        <span>転送先IPv4</span>
        <input data-field="target_host" required placeholder="192.168.0.100" value="${escapeHtml(rule.target_host ?? "")}">
      </label>
      <label>
        <span>転送先ポート</span>
        <input data-field="target_port" type="number" min="1" max="65535" required value="${escapeHtml(rule.target_port ?? "")}">
      </label>
      <button class="icon-button delete-port" type="button" aria-label="このルールを削除">削除</button>
    </article>`;
}

function errorMessage(error) {
  if (typeof error?.detail === "string") return error.detail;
  if (Array.isArray(error?.detail)) {
    return error.detail.map((item) => item.msg).join(" / ");
  }
  return "設定を処理できませんでした。";
}

async function loadPorts() {
  $("#ports-message").textContent = "設定を読み込んでいます…";
  try {
    const response = await fetch("/api/ports", { cache: "no-store" });
    const body = await response.json();
    if (!response.ok) throw body;
    $("#external-interface").value = body.external_interface;
    $("#masquerade").checked = body.masquerade;
    $("#port-rules").innerHTML = body.ports.map(portRule).join("");
    $("#ports-message").textContent = `${body.ports.length}件のルール`;
    portsLoaded = true;
  } catch (error) {
    $("#ports-message").textContent = `読込失敗: ${errorMessage(error)}`;
  }
}

function collectPorts() {
  return [...document.querySelectorAll(".port-rule")].map((rule) => ({
    protocol: rule.querySelector("[data-field=protocol]").value,
    external_port: Number(rule.querySelector("[data-field=external_port]").value),
    target_host: rule.querySelector("[data-field=target_host]").value.trim(),
    target_port: Number(rule.querySelector("[data-field=target_port]").value),
  }));
}

function route() {
  const requested = location.hash.slice(2);
  const name = ["overview", "bgp", "ports"].includes(requested)
    ? requested
    : "overview";
  document.querySelectorAll(".view").forEach((view) => {
    view.hidden = view.id !== `view-${name}`;
  });
  document.querySelectorAll("[data-route]").forEach((tab) => {
    const active = tab.dataset.route === name;
    tab.classList.toggle("active", active);
    if (active) {
      tab.setAttribute("aria-current", "page");
    } else {
      tab.removeAttribute("aria-current");
    }
  });
  if (name === "ports" && !portsLoaded) loadPorts();
}

async function refresh() {
  $("#error").hidden = true;

  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const status = await response.json();

    $("#hostname").textContent = status.hostname;
    $("#uptime").textContent = duration(status.uptimeSeconds);
    $("#load").textContent = status.loadAverage
      .map((item) => item.toFixed(2))
      .join(" / ");
    $("#updated").textContent = new Date(status.timestamp * 1000).toLocaleTimeString();
    $("#interfaces").innerHTML = status.interfaces.map(interfaceCard).join("");
    renderBgp(status.bgp);
    $("#health").textContent = "ONLINE";
    $("#health").className = "badge online";
  } catch (error) {
    $("#health").textContent = "OFFLINE";
    $("#health").className = "badge offline";
    $("#error").textContent = `ステータスを取得できません: ${error.message}`;
    $("#error").hidden = false;
  } finally {
    window.setTimeout(refresh, 5000);
  }
}

document.querySelectorAll("[data-route]").forEach((tab) => {
  tab.addEventListener("click", (event) => {
    event.preventDefault();
    const hash = `#/${tab.dataset.route}`;
    if (location.hash === hash) {
      route();
    } else {
      location.hash = hash;
    }
  });
});
$("#add-port").addEventListener("click", () => {
  $("#port-rules").insertAdjacentHTML("beforeend", portRule());
});
$("#port-rules").addEventListener("click", (event) => {
  const button = event.target.closest(".delete-port");
  if (button) button.closest(".port-rule").remove();
});
$("#ports-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#save-ports");
  button.disabled = true;
  $("#ports-message").textContent = "保存しています…";
  try {
    const response = await fetch("/api/ports", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        external_interface: $("#external-interface").value.trim(),
        masquerade: $("#masquerade").checked,
        ports: collectPorts(),
      }),
    });
    const body = await response.json();
    if (!response.ok) throw body;
    $("#ports-message").textContent =
      `${body.ports.length}件を保存しました。手動でrebuildしてください。`;
  } catch (error) {
    $("#ports-message").textContent = `保存失敗: ${errorMessage(error)}`;
  } finally {
    button.disabled = false;
  }
});
window.addEventListener("hashchange", route);
route();
refresh();
