const tg = window.Telegram?.WebApp;
const getConfiguredBackendUrl = () => (window.APP_CONFIG?.backendUrl || "").trim();
const getApiCandidates = () => {
  const configured = getConfiguredBackendUrl();
  const candidates = ["/api"];
  if (configured) candidates.push(`${configured.replace(/\/$/, "")}/api`);
  return [...new Set(candidates)];
};
const $ = (id) => document.getElementById(id);

let state = {
  user: null,
  adSession: null,
  adTimer: null,
  selectedFruit: 1,
};

const fruitSpecs = {
  1: { name: "Olma", ads: 3, reward: 5 },
  2: { name: "Nok", ads: 3, reward: 6 },
  3: { name: "Shaftoli", ads: 3, reward: 7 },
  4: { name: "Gilos", ads: 3, reward: 8 },
  5: { name: "Anor", ads: 3, reward: 10 },
};

function initData() {
  return tg?.initData || "";
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": initData(),
    ...(options.headers || {}),
  };

  let lastError = null;

  for (const base of getApiCandidates()) {
    try {
      const response = await fetch(`${base}${path}`, {
        ...options,
        headers,
      });

      const data = await response.json().catch(() => ({
        ok: false,
        error: "Server javobi noto'g'ri",
      }));

      if (response.ok && data.ok !== false) {
        return data;
      }

      lastError = new Error(data.error || "Xatolik yuz berdi");
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error("Serverga ulanib bo'lmadi");
}

function notify(message) {
  if (tg?.showAlert) tg.showAlert(message);
  else alert(message);
}

function renderUser(user) {
  if (!user) return;
  state.user = user;

  const apples = String(user.apples ?? 0);
  const ads = String(user.ads ?? 0);
  const pending = Number(user.pending_ads ?? 0);

  if ($("topFruitCount")) $("topFruitCount").textContent = apples;
  if ($("profileApples")) $("profileApples").textContent = apples;
  if ($("profileAds")) $("profileAds").textContent = ads;
  if ($("homeFruits")) $("homeFruits").textContent = apples;
  if ($("homeFruitsBadge")) $("homeFruitsBadge").textContent = apples;
  if ($("homeAds")) $("homeAds").textContent = ads;
  if ($("storageFruits")) $("storageFruits").textContent = apples;
  if ($("storageAvailable")) $("storageAvailable").textContent = apples;
  if ($("storageBalance")) $("storageBalance").textContent = apples;
  if ($("storageCurrent")) $("storageCurrent").textContent = apples;
  if ($("totalApple")) $("totalApple").textContent = apples;
  if ($("appleAmount")) $("appleAmount").textContent = apples;
  if ($("waterCount")) $("waterCount").textContent = user.water ?? 0;
  if ($("homeWaterEnergy")) $("homeWaterEnergy").textContent = `${user.water ?? 0}%`;
  if ($("inviteCount")) $("inviteCount").textContent = user.referrals ?? 0;

  const name = user.first_name || user.username || "Foydalanuvchi";
  if ($("profileName")) $("profileName").textContent = name;
  if ($("profileUsername")) $("profileUsername").textContent =
    user.username ? `@${user.username}` : "Telegram foydalanuvchisi";
  if ($("homeUserName")) $("homeUserName").textContent = name;

  const level = Number(user.level || 0);
  const xp = Number(user.apples || 0) % 100;
  document.querySelectorAll(".profile-progress .progress-head span")[0]?.replaceChildren(
    document.createTextNode(`Level ${level}`)
  );
  document.querySelectorAll(".profile-progress .progress-head span")[1]?.replaceChildren(
    document.createTextNode(`${xp} / 100 XP`)
  );
  const fill = document.querySelector(".profile-progress .progress-fill");
  if (fill) fill.style.width = `${xp}%`;

  updateAdUI(pending);
  updateDailyButton(user.daily_claimed);
  updateChannelButton(user.channel_claimed);
  renderLeaderboard(user.leaderboard || []);
  renderProfileAvatar(user);
}

function renderProfileAvatar(user) {
  const name = user.first_name || user.username || "U";
  const initial = name[0].toUpperCase();

  [$("profileBadge"), $("profilePageAvatar")].forEach((el) => {
    if (!el) return;
    if (user.photo_url) {
      el.innerHTML = `<img src="${escapeHtml(user.photo_url)}" alt="Profile">`;
    } else {
      el.innerHTML = `<span class="profile-badge__initial">${escapeHtml(initial)}</span>`;
    }
  });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[c]));
}

function updateAdUI(pending = Number(state.user?.pending_ads || 0)) {
  const btn = $("adBtn");
  const text = $("adBtnText");
  const status = $("statusText");
  const water = $("waterBtn");

  if (!btn || !text) return;

  if (state.adTimer) return;

  text.textContent = `Reklama ${pending}/3`;

  if (pending >= 3) {
    btn.disabled = true;
    btn.classList.add("completed");
    if (status) status.textContent = "3 ta reklama tugadi. Endi daraxtni sug'oring.";
    if (water) water.disabled = false;
  } else {
    btn.disabled = false;
    btn.classList.remove("completed");
    if (status) status.textContent =
      `Reklama ${pending}/3 — har biri ${15} soniya.`;
    if (water) water.disabled = true;
  }
}

async function startAd() {
  if (state.adTimer || Number(state.user?.pending_ads || 0) >= 3) return;

  try {
    const data = await api("/ad/start", { method: "POST" });
    state.adSession = data.session;

    let remaining = Number(data.seconds || 15);
    state.adTimer = setInterval(async () => {
      if ($("adBtnText")) $("adBtnText").textContent = `Kutilyapti ${remaining}s`;
      if ($("statusText")) $("statusText").textContent =
        `Reklama ko'rilmoqda — ${remaining} soniya qoldi.`;

      remaining -= 1;

      if (remaining < 0) {
        clearInterval(state.adTimer);
        state.adTimer = null;

        try {
          const result = await api("/ad/complete", {
            method: "POST",
            body: JSON.stringify({ session: state.adSession }),
          });
          state.adSession = null;
          renderUser(result.user);
          notify("Reklama hisoblandi ✅");
        } catch (error) {
          state.adSession = null;
          notify(error.message);
          updateAdUI();
        }
      }
    }, 1000);
  } catch (error) {
    notify(error.message);
  }
}

async function waterTree() {
  if (Number(state.user?.pending_ads || 0) < 3) {
    notify("Avval 3 ta reklama ko'ring.");
    return;
  }

  try {
    const result = await api("/water", {
      method: "POST",
      body: JSON.stringify({}),
    });
    renderUser(result.user);
    notify(`Daraxt sug'orildi! +${result.reward} 🍎`);
  } catch (error) {
    notify(error.message);
  }
}

async function claimDaily() {
  try {
    const result = await api("/daily", {
      method: "POST",
      body: JSON.stringify({}),
    });
    renderUser(result.user);
    notify(`Kunlik bonus: +${result.reward} 🍎`);
  } catch (error) {
    notify(error.message);
  }
}

function updateDailyButton(claimed) {
  const btn = $("dailyRewardBtn");
  if (!btn) return;
  const today = new Date().toISOString().slice(0, 10);
  if (claimed === today) {
    btn.disabled = true;
    btn.textContent = "Olingan";
  } else {
    btn.disabled = false;
    btn.textContent = "Olish";
  }
}

function updateChannelButton(claimed) {
  const btn = $("taskJoinChannel");
  if (!btn) return;
  if (claimed) {
    btn.disabled = true;
    btn.textContent = "Bajarildi";
  } else {
    btn.disabled = false;
    btn.textContent = "Bajarish";
  }
}

async function claimChannel() {
  const channel = window.CHANNEL_USERNAME || "";
  if (tg?.openTelegramLink && channel) {
    const link = channel.startsWith("@")
      ? `https://t.me/${channel.slice(1)}`
      : channel;
    tg.openTelegramLink(link);
  }

  // Telegram kanalga kirib bo'lgach yana tugmani bosib tekshirtiriladi.
  setTimeout(async () => {
    try {
      const result = await api("/channel/claim", {
        method: "POST",
        body: JSON.stringify({}),
      });
      renderUser(result.user);
      notify(`Vazifa bajarildi! +${result.reward} 🍎`);
    } catch (error) {
      notify(error.message);
    }
  }, 1200);
}

function renderLeaderboard(list) {
  const el = $("leaderboardList");
  if (!el) return;
  el.innerHTML = list.map((item, i) => {
    const medal = i === 0 ? "🥇" : i === 1 ? "🥈" : i === 2 ? "🥉" : `#${i + 1}`;
    return `<li><span class="medal">${medal}</span><strong>${escapeHtml(item.name)}</strong><span>${item.count}</span></li>`;
  }).join("");
}

function copyReferral() {
  const input = $("refLinkInput");
  if (!input) return;
  navigator.clipboard?.writeText(input.value);
  notify("Referal havola nusxalandi ✅");
}

function inviteFriend() {
  const link = $("refLinkInput")?.value;
  if (tg?.openTelegramLink && link) {
    tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent("🍎 Meva Garden")}`);
  } else if (navigator.share && link) {
    navigator.share({ title: "Meva Garden", url: link }).catch(() => {});
  } else {
    copyReferral();
  }
}

function setView(name) {
  const views = {
    garden: ".garden-view",
    home: ".home-view",
    bot: ".storage-view",
    profile: ".profile-view",
  };

  Object.values(views).forEach((selector) => {
    document.querySelector(selector)?.classList.add("hidden");
  });

  document.querySelector(views[name])?.classList.remove("hidden");

  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.nav === name);
  });

  if (name === "profile") renderUser(state.user);
}

function setupFruitSelection() {
  document.querySelectorAll(".fruit-selection-item").forEach((item) => {
    item.addEventListener("click", () => {
      if (item.classList.contains("locked")) {
        notify("Bu meva hali qulflangan.");
        return;
      }

      document.querySelectorAll(".fruit-selection-item")
        .forEach((x) => x.classList.remove("active"));
      item.classList.add("active");

      state.selectedFruit = Number(item.dataset.fruitId || 1);
      const fruit = fruitSpecs[state.selectedFruit];

      if ($("mainStatusTitle"))
        $("mainStatusTitle").textContent = `${fruit.name} Tanlandi — 15 s`;

      updateAdUI(state.user?.pending_ads || 0);
    });
  });
}

async function load() {
  const loadingOverlay = document.getElementById("loadingOverlay");

  if (!tg?.initData) {
    if (loadingOverlay) loadingOverlay.remove();
    notify("Mini Appni Telegram ichidan oching. Oddiy brauzerda server autentifikatsiyasi ishlamaydi.");
    return;
  }

  try {
    const startParam = tg.initDataUnsafe?.start_param || "";
    const result = await api(`/me?start_param=${encodeURIComponent(startParam)}`);
    state.user = result.user;

    const refInput = $("refLinkInput");
    if (refInput) refInput.value = result.user.ref_link || "";

    renderUser(result.user);
  } catch (error) {
    notify(error.message);
  } finally {
    if (loadingOverlay) loadingOverlay.remove();
  }
}

if (tg) {
  tg.ready();
  tg.expand();
  try {
    tg.setHeaderColor("secondary_bg_color");
    tg.setBackgroundColor("secondary_bg_color");
  } catch (_) {}
}

$("adBtn")?.addEventListener("click", startAd);
$("homeAdBtn")?.addEventListener("click", startAd);
$("waterBtn")?.addEventListener("click", waterTree);
$("dailyRewardBtn")?.addEventListener("click", claimDaily);
$("taskJoinChannel")?.addEventListener("click", claimChannel);
$("inviteFriendBtn")?.addEventListener("click", inviteFriend);
document.querySelector(".btn-copy-link")?.addEventListener("click", copyReferral);

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.nav));
});

$("homeGardenBtn")?.addEventListener("click", () => setView("garden"));
$("storageGardenBtn")?.addEventListener("click", () => setView("garden"));
$("backToGardenBtn")?.addEventListener("click", () => setView("garden"));

setupFruitSelection();
load();
