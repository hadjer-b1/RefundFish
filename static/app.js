// RefundFish Web App JavaScript

// Global state
let currentSettings = {};
let searchInProgress = false;
let monitoringPollingTimer = null;

// Initialize app
document.addEventListener("DOMContentLoaded", function () {
  loadSettings();
  loadHistory();
  loadCredentials();
  loadMonitoringStatus();
  loadActivityLog();
  setupEventListeners();
  checkStatus();

  if (monitoringPollingTimer) {
    clearInterval(monitoringPollingTimer);
  }
  monitoringPollingTimer = setInterval(() => {
    loadMonitoringStatus();
    loadActivityLog();
  }, 15000);
});

// Setup event listeners
function setupEventListeners() {
  document.getElementById("min_savings").addEventListener("input", function () {
    document.getElementById("savings_value").textContent = "$" + this.value;
  });
}

// Load settings from server
async function loadSettings() {
  try {
    const response = await fetch("/api/settings");
    const settings = await response.json();
    currentSettings = settings;

    // Update UI
    document.getElementById("min_savings").value =
      settings.min_savings_threshold;
    document.getElementById("savings_value").textContent =
      "$" + settings.min_savings_threshold;
    document.getElementById("selected_website").value =
      settings.selected_website;
    document.getElementById("refund_enabled").checked = settings.refund_enabled;
    document.getElementById("auto_refund").checked = settings.auto_refund;
  } catch (error) {
    console.error("Error loading settings:", error);
  }
}

// Save settings
async function saveSettings() {
  const settings = {
    min_savings_threshold: parseFloat(
      document.getElementById("min_savings").value,
    ),
    selected_website: document.getElementById("selected_website").value,
    refund_enabled: document.getElementById("refund_enabled").checked,
    auto_refund: document.getElementById("auto_refund").checked,
  };

  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });

    const result = await response.json();
    currentSettings = result.settings;
    showStatus("Settings saved!", "success");
    addLog("Settings updated", "success");
  } catch (error) {
    console.error("Error saving settings:", error);
    showStatus("Error saving settings", "error");
  }
}

// Search hotel
async function searchHotel() {
  const hotel_name = document.getElementById("hotel_name").value;
  const dates = document.getElementById("dates").value;
  const paid_price = document.getElementById("paid_price").value;
  const booking_id = document.getElementById("booking_id").value;

  if (!hotel_name || !dates || !paid_price) {
    showStatus("Please fill all fields", "error");
    return;
  }

  if (searchInProgress) return;

  searchInProgress = true;
  document.getElementById("search_btn").disabled = true;

  showStatus("🔍 Searching...", "loading");
  addLog(`Searching for ${hotel_name} on ${dates}...`, "info");
  updateStatusBar(true, "Searching...");

  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        hotel_name: hotel_name,
        dates: dates,
        paid_price: paid_price,
        booking_id: booking_id,
      }),
    });

    const result = await response.json();

    if (response.ok) {
      displayResults(result);
      showStatus("✓ Search completed!", "success");
      addLog(`Found price: $${result.current_price}`, "success");

      // Show auto-refund status if applicable
      if (
        result.auto_refund_status &&
        result.auto_refund_status !== "pending"
      ) {
        addLog(
          `Auto-refund: ${result.message}`,
          result.auto_refund_status === "success" ? "success" : "warning",
        );
      }

      loadHistory();
    } else {
      const errorMsg = result.details || result.error || "Unknown error occurred";
      showStatus("❌ " + errorMsg, "error");
      addLog(errorMsg, "error");
    }
  } catch (error) {
    console.error("Search error:", error);
    const errorMsg = `Search failed: ${error.message || "JSON parse error - service may be unavailable"}`;
    showStatus(errorMsg, "error");
    addLog(errorMsg, "error");
  } finally {
    searchInProgress = false;
    document.getElementById("search_btn").disabled = false;
    updateStatusBar(false, "Ready");
  }
}

// Display results
function displayResults(result) {
  const container = document.getElementById("results");

  const savings_color = result.net_savings > 0 ? "positive" : "negative";
  const recommendation_class =
    result.recommendation === "REBOOK" ? "rebook" : "keep";

  const auto_refund_message =
    result.auto_refund_status && result.auto_refund_status !== "pending"
      ? `<div class="auto-refund-note" style="margin-top: 15px; padding: 10px; background: ${result.auto_refund_status === "success" ? "#d4edda" : "#fff3cd"}; border-radius: 6px; border-left: 3px solid ${result.auto_refund_status === "success" ? "#28a745" : "#ffc107"};">
           <strong>${result.auto_refund_status === "success" ? "✓" : "⚠"} Auto-Refund:</strong> ${result.message}
           </div>`
      : "";

  const html = `
        <div class="result-card">
            <div class="result-row">
                <span class="result-label">Hotel</span>
                <span class="result-value">${result.hotel}</span>
            </div>
            <div class="result-row">
                <span class="result-label">Dates</span>
                <span class="result-value">${result.dates}</span>
            </div>
            <div class="result-row">
                <span class="result-label">Paid Price</span>
                <span class="result-value">$${result.paid_price.toFixed(2)}</span>
            </div>
            <div class="result-row">
                <span class="result-label">Current Price</span>
                <span class="result-value">$${result.current_price.toFixed(2)}</span>
            </div>
            <div class="result-row">
                <span class="result-label">Gross Savings</span>
                <span class="result-value positive">$${result.gross_savings.toFixed(2)}</span>
            </div>
            <div class="result-row">
                <span class="result-label">Savings %</span>
                <span class="result-value positive">${result.savings_percent.toFixed(1)}%</span>
            </div>
            <div class="result-row">
                <span class="result-label">Threshold</span>
                <span class="result-value">$${result.threshold.toFixed(2)}</span>
            </div>
            <div class="result-row">
                <span class="result-label">Net Savings</span>
                <span class="result-value ${savings_color}">$${result.net_savings.toFixed(2)}</span>
            </div>
            <div class="result-row">
                <span class="result-label">Meets Threshold</span>
                <span class="result-value">${result.meets_threshold ? "✓ YES" : "✗ NO"}</span>
            </div>
            <div class="recommendation ${recommendation_class}">
                📋 ${result.recommendation}
                ${result.recommendation === "REBOOK" ? `(Save $${result.net_savings.toFixed(2)})` : "(Not enough savings)"}
            </div>
            ${auto_refund_message}
        </div>
    `;

  container.innerHTML = html;
}

// Add log entry
function addLog(message, type = "info") {
  const logs = document.getElementById("logs");
  const timestamp = new Date().toLocaleTimeString();
  const entry = document.createElement("div");
  entry.className = `log-entry ${type}`;
  entry.textContent = `[${timestamp}] ${message}`;
  logs.appendChild(entry);
  logs.scrollTop = logs.scrollHeight;

  // Keep only last 50 logs
  while (logs.children.length > 50) {
    logs.removeChild(logs.firstChild);
  }
}

// Load search history
async function loadHistory() {
  try {
    const response = await fetch("/api/history");
    const history = await response.json();

    const historyList = document.getElementById("history_list");
    historyList.innerHTML = "";

    if (history.length === 0) {
      historyList.innerHTML = '<div class="placeholder">No searches yet</div>';
      return;
    }

    // Show last 10
    history
      .slice(-10)
      .reverse()
      .forEach((item) => {
        const div = document.createElement("div");
        div.className = "history-item";
        div.innerHTML = `
                <div class="history-item-title">${item.hotel}</div>
                <div class="history-item-meta">
                    Saved: $${item.net_savings.toFixed(2)} | ${item.recommendation}
                </div>
            `;
        historyList.appendChild(div);
      });
  } catch (error) {
    console.error("Error loading history:", error);
  }
}

// Clear history
async function clearHistory() {
  if (!confirm("Clear all search history?")) return;

  try {
    await fetch("/api/clear-history", { method: "POST" });
    loadHistory();
    showStatus("History cleared", "success");
    addLog("Search history cleared", "info");
  } catch (error) {
    console.error("Error clearing history:", error);
  }
}

// Fetch reservations from user's account
let fetchInProgress = false;
async function fetchReservations() {
  const website = document.getElementById("fetch_website").value;

  if (fetchInProgress) return;

  fetchInProgress = true;
  document.getElementById("fetch_btn").disabled = true;

  showStatus("🔗 Connecting to your account...", "loading", "fetch_status");
  addLog(`Fetching reservations from ${website}...`, "info");
  updateStatusBar(true, "Fetching reservations...");

  try {
    const response = await fetch("/api/fetch-reservations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ website: website }),
    });

    const result = await response.json();

    if (result.status === "success" && result.reservations.length > 0) {
      // Store reservations in global variable
      window.fetchedReservations = result.reservations;

      // Populate the select dropdown
      const select = document.getElementById("reservation_select");
      select.innerHTML = '<option value="">-- Select a reservation --</option>';

      result.reservations.forEach((res, index) => {
        const option = document.createElement("option");
        option.value = index;
        option.textContent = `${res.hotel_name} (${res.dates}) - $${res.paid_price.toFixed(2)}`;
        select.appendChild(option);
      });

      // Show the reservations list
      document.getElementById("reservations_list").style.display = "block";

      showStatus(
        `✓ Found ${result.count} reservation(s)!`,
        "success",
        "fetch_status",
      );
      addLog(`Found ${result.count} active reservation(s)`, "success");
    } else if (result.status === "no_reservations") {
      showStatus(`⚠ No active reservations found.`, "warning", "fetch_status");
      addLog(
        "No active reservations found - check your account manually",
        "warning",
      );
      document.getElementById("reservations_list").style.display = "none";
    } else {
      showStatus(`❌ ${result.error}`, "error", "fetch_status");
      addLog(`Error: ${result.error}`, "error");
      document.getElementById("reservations_list").style.display = "none";
    }
  } catch (error) {
    console.error("Fetch error:", error);
    showStatus(
      "❌ Error connecting to account: " + error.message,
      "error",
      "fetch_status",
    );
    addLog("Failed to fetch reservations: " + error.message, "error");
  } finally {
    fetchInProgress = false;
    document.getElementById("fetch_btn").disabled = false;
    updateStatusBar(false, "Ready");
  }
}

// Select a reservation and auto-populate fields
function selectReservation() {
  const index = document.getElementById("reservation_select").value;

  if (index === "") {
    // Clear fields
    document.getElementById("hotel_name").value = "";
    document.getElementById("dates").value = "";
    document.getElementById("paid_price").value = "";
    document.getElementById("booking_id").value = "";
    return;
  }

  const res = window.fetchedReservations[parseInt(index)];

  // Auto-populate the search fields
  document.getElementById("hotel_name").value = res.hotel_name;
  document.getElementById("dates").value = res.dates;
  document.getElementById("paid_price").value = res.paid_price;
  document.getElementById("booking_id").value = res.booking_id;
  document.getElementById("fetch_website").value =
    currentSettings.selected_website || "booking.com";

  addLog(`Selected: ${res.hotel_name} for ${res.dates}`, "info");
  showStatus(
    `✓ Ready to search! Click "Search Price" to check current rates.`,
    "success",
    "fetch_status",
  );
}

// Show status message
function showStatus(message, type, elementId) {
  const elementToUpdate = elementId || "search_status";
  const status = document.getElementById(elementToUpdate);
  if (!status) {
    console.error(`Status element ${elementToUpdate} not found`);
    return;
  }
  status.textContent = message;
  status.className = `status-message show ${type}`;

  if (type !== "loading") {
    setTimeout(() => {
      status.classList.remove("show");
    }, 5000);
  }
}

// Update status bar
function updateStatusBar(active, text) {
  const dot = document.querySelector(".status-dot");
  const statusText = document.getElementById("status_text");

  statusText.textContent = text;
  if (active) {
    dot.style.background = "#3498db";
  } else {
    dot.style.background = "#27ae60";
  }
}

// ============ CREDENTIALS MANAGEMENT ============

// Load and display saved credentials
async function loadCredentials() {
  try {
    const response = await fetch("/api/credentials/list");
    const data = await response.json();

    const credList = document.getElementById("cred_list");
    credList.innerHTML = "";

    // Update header badge
    const savedCount = data.credentials ? data.credentials.length : 0;
    updateCredentialStatus(savedCount);

    if (!data.credentials || data.credentials.length === 0) {
      credList.innerHTML =
        '<div class="placeholder">No saved credentials yet</div>';
      document.getElementById("cred_saved_count").style.display = "none";
      return;
    }

    document.getElementById("cred_saved_count").style.display = "inline-block";

    data.credentials.forEach((cred) => {
      const div = document.createElement("div");
      div.className = "cred-item";
      div.innerHTML = `
                <div class="cred-item-header">
                    <span class="cred-website">${cred.website}</span>
                    <span class="cred-username">👤 ${cred.username}</span>
                </div>
                <div class="cred-item-actions">
                    <button class="btn btn-small btn-danger-delete" onclick="deleteCredential('${cred.website}')">🗑️</button>
                </div>
            `;
      credList.appendChild(div);
    });
  } catch (error) {
    console.error("Error loading credentials:", error);
    addLog("Error loading credentials: " + error.message, "error");
  }
}

// Update header credential status badge
function updateCredentialStatus(count) {
  const badge = document.getElementById("cred_status_indicator");
  if (count > 0) {
    badge.innerHTML = `<i class="material-icons icon-small">verified_user</i>${count} Account${count !== 1 ? "s" : ""} Connected`;
    badge.className = "cred-badge set";
  } else {
    badge.innerHTML =
      '<i class="material-icons icon-small">lock_open</i>No Credentials';
    badge.className = "cred-badge not-set";
  }
}

// Toggle password visibility
function togglePasswordVisibility() {
  const passwordInput = document.getElementById("cred_password");
  const toggleIcon = document.querySelector(".toggle-password .material-icons");

  if (passwordInput.type === "password") {
    passwordInput.type = "text";
    if (toggleIcon) toggleIcon.textContent = "visibility_off";
  } else {
    passwordInput.type = "password";
    if (toggleIcon) toggleIcon.textContent = "visibility";
  }
}

// Save new credentials
async function saveCredentials() {
  const website = document.getElementById("credential_website").value;
  const username = document.getElementById("cred_username").value;
  const password = document.getElementById("cred_password").value;
  const twofa_code = document.getElementById("cred_2fa_code").value;

  if (!website || !username) {
    showStatus(
      "❌ Please select website and enter email/username",
      "error",
      "cred_status_message",
    );
    return;
  }

  try {
    const response = await fetch("/api/credentials/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        website: website,
        username: username,
        password: password || null,
        two_fa_code: twofa_code || null,
      }),
    });

    const result = await response.json();

    if (response.ok) {
      let authMethod = "Email saved";
      if (twofa_code) authMethod = "2FA Code";
      else if (password) authMethod = "Password";

      showStatus(
        `✓ Secure! Credentials saved for ${website} (${authMethod})`,
        "success",
        "cred_status_message",
      );
      addLog(`✓ Credentials saved for ${website}`, "success");
      document.getElementById("credential_website").value = "";
      document.getElementById("cred_username").value = "";
      document.getElementById("cred_password").value = "";
      document.getElementById("cred_2fa_code").value = "";
      loadCredentials();
    } else {
      showStatus(`✗ Error: ${result.error}`, "error", "cred_status_message");
      addLog(`✗ Error: ${result.error}`, "error");
    }
  } catch (error) {
    console.error("Error saving credentials:", error);
    showStatus(
      "❌ Error saving credentials: " + error.message,
      "error",
      "cred_status_message",
    );
    addLog("Error saving credentials: " + error.message, "error");
  }
}

// Delete credentials
async function deleteCredential(website) {
  if (!confirm(`Delete credentials for ${website}?`)) return;

  try {
    const response = await fetch(`/api/credentials/delete/${website}`, {
      method: "DELETE",
    });

    const result = await response.json();

    if (response.ok) {
      addLog(`✓ Credentials deleted for ${website}`, "success");
      loadCredentials();
    } else {
      addLog(`✗ Error: ${result.error}`, "error");
    }
  } catch (error) {
    console.error("Error deleting credentials:", error);
    addLog("Error deleting credentials: " + error.message, "error");
  }
}

// Check system status
async function checkStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();

    if (!status.api_configured) {
      addLog("⚠️ WARNING: TinyFish API not configured", "warning");
    }
  } catch (error) {
    console.error("Error checking status:", error);
  }
}

async function toggleMonitoring(enabled) {
  const hotelName = document.getElementById("hotel_name").value;
  const dates = document.getElementById("dates").value;
  const bookingUrl = document.getElementById("booking_url").value;
  const targetPrice = document.getElementById("target_price").value;
  const paidPrice = document.getElementById("paid_price").value;
  const bookingId = document.getElementById("booking_id").value;
  const website = document.getElementById("selected_website").value;
  const statusText = document.getElementById("monitoring_status");

  try {
    if (enabled) {
      if (!targetPrice || (!bookingUrl && (!hotelName || !dates))) {
        showStatus(
          "Provide Target Price, and either Booking URL OR Hotel Name + Dates",
          "error",
          "search_status",
        );
        document.getElementById("monitoring_toggle").checked = false;
        return;
      }

      const response = await fetch("/api/monitoring/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hotel_name: hotelName,
          dates: dates,
          booking_url: bookingUrl,
          target_price: targetPrice,
          paid_price: paidPrice,
          booking_id: bookingId,
          website: website,
        }),
      });
      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Failed to start monitoring");
      }

      statusText.textContent = "Live Monitor is running with session cookies";
      addLog("Live Monitor started", "success");
      showStatus(
        `Monitoring: ${hotelName || "Selected Hotel"} - Looking for price under $${Number(targetPrice).toFixed(2)}...`,
        "success",
        "search_status",
      );
    } else {
      const response = await fetch("/api/monitoring/stop", {
        method: "POST",
      });
      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || "Failed to stop monitoring");
      }

      statusText.textContent = "Live Monitor is stopped";
      addLog("Live Monitor stopped", "warning");
      showStatus("Live Monitor stopped", "success", "search_status");
    }

    loadMonitoringStatus();
    loadActivityLog();
  } catch (error) {
    console.error("Monitoring toggle error:", error);
    addLog(`Monitoring error: ${error.message}`, "error");
    showStatus(error.message, "error", "search_status");
    document.getElementById("monitoring_toggle").checked = !enabled;
  }
}

async function loadMonitoringStatus() {
  const toggle = document.getElementById("monitoring_toggle");
  const statusText = document.getElementById("monitoring_status");
  const liveStatusText = document.getElementById("live_status_text");
  const currentLivePriceEl = document.getElementById("current_live_price");
  const dropNotice = document.getElementById("price_drop_notice");
  const executeBtn = document.getElementById("execute_rebook_btn");
  if (!toggle || !statusText) return;

  try {
    const response = await fetch("/api/monitoring/status");
    const status = await response.json();

    toggle.checked = Boolean(status.enabled);

    if (liveStatusText) {
      liveStatusText.textContent = "Connected via Session Cookies";
    }

    if (currentLivePriceEl) {
      currentLivePriceEl.value =
        status.current_live_price !== null &&
        status.current_live_price !== undefined
          ? Number(status.current_live_price).toFixed(2)
          : "";
    }

    if (dropNotice && executeBtn) {
      if (status.price_drop_detected) {
        dropNotice.style.display = "block";
        executeBtn.style.display = "flex";
      } else {
        dropNotice.style.display = "none";
        executeBtn.style.display = "none";
      }
    }

    if (status.enabled) {
      const targetHotel = status.target?.hotel_name || "Selected Hotel";
      const targetPrice = status.target?.target_price;
      const targetText =
        targetPrice !== null && targetPrice !== undefined
          ? `$${Number(targetPrice).toFixed(2)}`
          : "target";
      statusText.textContent = `Monitoring: ${targetHotel} - Looking for price under ${targetText}...`;
    } else {
      statusText.textContent = "Live Monitor is stopped";
    }
  } catch (error) {
    console.error("Failed to load monitoring status:", error);
  }
}

async function executeAutoRebook() {
  const payload = {
    hotel_name: document.getElementById("hotel_name").value,
    dates: document.getElementById("dates").value,
    website: document.getElementById("selected_website").value,
    booking_id: document.getElementById("booking_id").value,
    booking_url: document.getElementById("booking_url").value,
    current_live_price: document.getElementById("current_live_price").value,
    paid_price: document.getElementById("paid_price").value,
  };

  try {
    showStatus(
      "Executing Smart Wishlist Hunter...",
      "loading",
      "search_status",
    );
    addLog("Executing Smart Wishlist Hunter action...", "info");

    const response = await fetch("/api/live-monitor/execute-smart-wishlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();

    if (!response.ok || result.status !== "success") {
      throw new Error(result.error || "Smart Wishlist Hunter failed");
    }

    showStatus(`Success: ${result.message}`, "success", "search_status");
    addLog(`Auto-rebook success: ${result.message}`, "success");
    loadMonitoringStatus();
    loadActivityLog();
  } catch (error) {
    console.error("Execute auto-rebook failed:", error);
    showStatus(error.message, "error", "search_status");
    addLog(`Auto-rebook failed: ${error.message}`, "error");
  }
}

async function loadActivityLog() {
  const container = document.getElementById("activity_log");
  if (!container) return;

  try {
    const response = await fetch("/api/activity-log?limit=60");
    const logs = await response.json();

    if (!Array.isArray(logs) || logs.length === 0) {
      container.innerHTML = '<div class="placeholder">No activity yet</div>';
      return;
    }

    const rows = logs
      .slice()
      .reverse()
      .map((entry) => {
        const ts = entry.timestamp
          ? new Date(entry.timestamp).toLocaleString()
          : "-";
        const statusClass = `status-chip ${entry.status || "info"}`;
        const formattedLine =
          entry.log_line ||
          entry.message ||
          `[${ts}] | Hotel: ${entry.hotel || "N/A"} | Price: ${entry.current_price ? `$${Number(entry.current_price).toFixed(2)}` : "N/A"} | Status: ${entry.status || "info"}`;
        return `
          <div class="activity-row">
            <div class="activity-meta">
              <span class="activity-time">${ts}</span>
              <span class="${statusClass}">${entry.status || "info"}</span>
            </div>
            <div class="activity-message">${formattedLine}</div>
          </div>
        `;
      })
      .join("");

    container.innerHTML = rows;
  } catch (error) {
    console.error("Failed to load activity log:", error);
    container.innerHTML =
      '<div class="placeholder">Failed to load activity log</div>';
  }
}
