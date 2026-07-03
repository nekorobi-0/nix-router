const $ = (selector) => document.querySelector(selector);

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

function renderBgp(bgp) {
  if (!bgp?.available) {
    $("#bgp-summary").textContent = "取得不可";
    $("#bgp").innerHTML = "<p class=\"empty\">FRRからBGPステータスを取得できません。</p>";
    return;
  }

  $("#bgp-summary").textContent =
    `Router ID ${bgp.routerId || "—"} · AS${bgp.localAs ?? "—"} · ${bgp.peers.length} peer`;
  $("#bgp").innerHTML = bgp.peers.length
    ? bgp.peers.map(bgpPeerCard).join("")
    : "<p class=\"empty\">BGPピアが設定されていません。</p>";
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
    window.setTimeout(refresh, 500);
  }
}

refresh();
