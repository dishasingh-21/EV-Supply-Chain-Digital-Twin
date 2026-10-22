console.log("SCRIPT LOADED");

const params = new URLSearchParams(window.location.search);
const start = params.get("start");
const end = params.get("end");
const batteryPercent = parseFloat(params.get("battery"));

const API_BASE_URL = window.API_BASE_URL || "http://localhost:5000/api";

//Leaflet.js part — unchanged from the original.
var map = L.map('map').setView([26.5, 74.5], 6);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

function updateStatus(text, color = "var(--primary)") {
    const statusText = document.getElementById("status-text");
    const statusDot = document.getElementById("status-dot");
    if (statusText) statusText.innerText = text;
    if (statusDot) statusDot.style.background = color;
}

// A "lat,lon" string (e.g. "26.9124, 75.7873") in the Ending Destination
// field is treated as a delivery point given directly as coordinates,
// matching the field's existing free-text behavior — anything else is
// still geocoded as a place name, so the original planner keeps working
// exactly as before.
function parseLatLon(text) {
    const m = text.trim().match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
    if (!m) return null;
    const lat = parseFloat(m[1]);
    const lon = parseFloat(m[2]);
    if (Number.isNaN(lat) || Number.isNaN(lon)) return null;
    return { lat, lon };
}

async function findWarehouseByName(name) {
    try {
        const res = await fetch(`${API_BASE_URL}/warehouses`);
        const data = await res.json();
        const match = (data.warehouses || []).find(
            (w) => w.name.toLowerCase() === name.trim().toLowerCase() || w.code.toLowerCase() === name.trim().toLowerCase()
        );
        return match || null;
    } catch (err) {
        return null;
    }
}

//Draw Route — same marker/polyline/popup behavior as the original drawRoute,
//just fed from the backend's `legs`/`route` payload instead of doing the
//OSRM calls in the browser.
function drawRoute(route, legs) {
    let fullPath = [];

    legs.forEach((leg) => {
        if (leg.geometry) {
            leg.geometry.forEach((c) => {
                const pt = [c[1], c[0]];
                if (fullPath.length > 0) {
                    const last = fullPath[fullPath.length - 1];
                    if (last[0] === pt[0] && last[1] === pt[1]) return;
                }
                fullPath.push(pt);
            });
        } else {
            // OSRM was unreachable for this leg on the backend; fall back to a
            // straight line between the two endpoints so the map still renders.
            fullPath.push([leg.from.lat, leg.from.lon]);
            fullPath.push([leg.to.lat, leg.to.lon]);
        }

        const geomForMid = leg.geometry || [[leg.from.lon, leg.from.lat], [leg.to.lon, leg.to.lat]];
        const midcoords = geomForMid[Math.floor(geomForMid.length / 2)];
        const mid = [midcoords[1], midcoords[0]];
        L.marker(mid).addTo(map).bindPopup(
            `Distance: ${leg.distanceKm.toFixed(1)} km`
        );
    });

    const poly = L.polyline(fullPath, {
        color: 'black',
        weight: 6
    }).addTo(map);
    map.fitBounds(poly.getBounds());

    route.forEach((p, index) => {
        const isStart = index === 0;
        const isEnd = index === route.length - 1;
        const isCharging = p.isCharging;
        let color = "blue";
        if (isStart) color = "green";
        else if (isEnd) color = "red";
        else if (isCharging) color = "orange";
        const icon = L.circleMarker([p.lat, p.lon], {
            radius: 8,
            color: color,
            fillColor: color,
            fillOpacity: 1
        }).addTo(map);
        icon.bindPopup(`${p.name || "Charging Station"}`);
        if (isCharging) {
            icon.bindTooltip(p.name || "Charging Station", {
                permanent: true,
                direction: "top",
                offset: [0, -10],
                className: "station-label"
            });
        }
    });
}

function renderStats(result) {
    document.getElementById("distance").innerText = result.totalDistanceKm.toFixed(1);

    const hours = Math.floor(result.etaMinutes / 60);
    const mins = Math.round(result.etaMinutes % 60);
    document.getElementById("eta").innerText = `${hours}h ${mins}m`;

    const totalEtaElem = document.getElementById("total-eta");
    if (totalEtaElem) {
        totalEtaElem.innerText = `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')} hrs`;
    }
}

async function callRouteApi(body) {
    const res = await fetch(`${API_BASE_URL}/route`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Route planning failed");
    return data;
}

async function callDeliveryRouteApi(body) {
    const res = await fetch(`${API_BASE_URL}/route/delivery`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Delivery route planning failed");
    return data;
}

//starter function.
async function init() {
    console.log("INIT RUNNING");

    if (!start || !end || Number.isNaN(batteryPercent)) {
        updateStatus("Missing route parameters", "var(--danger)");
        alert("Missing start, end, or battery parameters.");
        return;
    }

    updateStatus("Planning Route...", "var(--accent)");

    // Delivery mode: Starting Point names a known warehouse AND Ending
    // Destination is given as "lat,lon". Falls back to the original
    // place-to-place geocoded planner for every other input combination,
    // so existing behavior is unchanged unless both conditions are met.
    const deliveryCoords = parseLatLon(end);
    const warehouse = deliveryCoords ? await findWarehouseByName(start) : null;

    let result;
    try {
        if (warehouse && deliveryCoords) {
            updateStatus("Optimizing Pickup Route...", "var(--accent)");
            result = await callDeliveryRouteApi({
                warehouseCode: warehouse.code,
                deliveryLat: deliveryCoords.lat,
                deliveryLon: deliveryCoords.lon,
                batteryPercent
            });
        } else {
            updateStatus("Geocoding Locations...", "var(--accent)");
            result = await callRouteApi({
                startPlace: start,
                endPlace: end,
                batteryPercent
            });
        }
    } catch (err) {
        console.error(err);
        updateStatus("Route Planning Failed", "var(--danger)");
        alert(err.message || "Could not plan a route with the given inputs.");
        return;
    }

    updateStatus(result.viaDirectRoute ? "Direct Route Found" : "Route Optimized via Stations", "var(--success)");
    updateStatus("Drawing Path...", "var(--accent)");
    drawRoute(result.route, result.legs);
    renderStats(result);
    updateStatus("Route Optimized", "var(--success)");
    console.log("Route:", result.route);
}

init();
