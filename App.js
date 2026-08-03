import React, { useState, useEffect, useRef } from "react";
import io from "socket.io-client";

const API_URL = "https://samudra-backend.onrender.com";

export default function FleetDashboard() {
  const [vessels, setVessels] = useState([]);
  const [selectedVessel, setSelectedVessel] = useState(null);
  const [weather, setWeather] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [showEmergencyConfirm, setShowEmergencyConfirm] = useState(null);
  const [showChat, setShowChat] = useState(false);
  const [chatMessage, setChatMessage] = useState("");
  const [messages, setMessages] = useState({});
  const [viewMode, setViewMode] = useState("table");
  const [showVesselHistory, setShowVesselHistory] = useState(false);
  const [vesselTracks, setVesselTracks] = useState({});
  const [language, setLanguage] = useState("en");
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [notifications, setNotifications] = useState([]);
  const [backendConnected, setBackendConnected] = useState(false);
  const [socketConnected, setSocketConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [socket, setSocket] = useState(null);
  const canvasRef = useRef(null);

  const baseCoast = { lat: 9.9865, lon: 76.3047 };

  const translations = {
    en: {
      title: "Samudra Rakshak Fleet Management",
      fleetStatus: "Fleet Status",
      currentWeather: "Current Weather",
      forecast: "4-Day Forecast",
      vesselDetails: "Vessel Details",
      activeAlerts: "Active Alerts",
      communication: "Vessel Communication",
      emergency: "EMERGENCY ALERT",
      export: "EXPORT",
      chat: "CHAT",
    },
    // ... other languages remain same
  };

  const t = translations[language];

  // ==================== WEBSOCKET CONNECTION ====================
  useEffect(() => {
    console.log("🔌 Base Station: Connecting to WebSocket...");

    const newSocket = io(API_URL, {
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionAttempts: 10,
    });

    newSocket.on("connect", () => {
      console.log("✅ Base Station: WebSocket Connected! ID:", newSocket.id);
      setSocketConnected(true);
      setBackendConnected(true);

      // Request all current data
      newSocket.emit("request_all_data");
    });

    newSocket.on("disconnect", () => {
      console.log("❌ Base Station: WebSocket Disconnected");
      setSocketConnected(false);
    });

    newSocket.on("connect_error", (error) => {
      console.error("🔴 Base Station: WebSocket Connection Error:", error);
      setSocketConnected(false);
    });

    // Listen for vessel updates
    newSocket.on("vessel_update", (data) => {
      console.log("🚢 Base Station: Received vessel update:", data);

      // Update vessels list with new data
      setVessels((prev) => {
        const existingIndex = prev.findIndex((v) => v.id === data.id);
        if (existingIndex >= 0) {
          // Update existing vessel
          const updated = [...prev];
          updated[existingIndex] = {
            ...updated[existingIndex],
            lat: data.lat || updated[existingIndex].lat,
            lon: data.lon || updated[existingIndex].lon,
            battery: data.battery || updated[existingIndex].battery,
            speed: data.speed || updated[existingIndex].speed,
            turbidity: data.turb,
            temperature: data.temp,
            pH: data.pH,
          };
          return updated;
        } else {
          // Add new vessel
          return [
            ...prev,
            {
              id: data.id || `FV-${Date.now()}`,
              name: data.name || "Unknown Vessel",
              lat: data.lat || 10.0,
              lon: data.lon || 76.0,
              battery: data.battery || 50,
              speed: data.speed || 0,
              heading: data.heading || 0,
              image: "🚢",
            },
          ];
        }
      });

      // Update vessel tracks
      if (data.lat && data.lon) {
        setVesselTracks((prev) => ({
          ...prev,
          [data.id]: [
            ...(prev[data.id] || []),
            { lat: data.lat, lon: data.lon },
          ].slice(-50), // Keep last 50 positions
        }));
      }
    });

    // Listen for buoy updates
    newSocket.on("buoy_update", (data) => {
      console.log("🎯 Base Station: Received buoy update:", data);
      // Handle buoy data if needed
    });

    // Listen for base station updates (from other base stations if any)
    newSocket.on("basestation_update", (data) => {
      console.log("📡 Base Station: Received base station update:", data);
    });

    // Listen for all data (initial load)
    newSocket.on("all_data", (data) => {
      console.log("📦 Base Station: Received all data:", data);

      if (data.vessel && Object.keys(data.vessel).length > 0) {
        // Add/update vessel from backend
        const vesselData = data.vessel;
        setVessels((prev) => {
          const existingIndex = prev.findIndex((v) => v.id === vesselData.id);
          const newVessel = {
            id: vesselData.id || `FV-${Date.now()}`,
            name: vesselData.name || "Unknown Vessel",
            lat: vesselData.lat || 10.0,
            lon: vesselData.lon || 76.0,
            battery: vesselData.battery || 50,
            speed: vesselData.speed || 0,
            heading: vesselData.heading || 0,
            image: "🚢",
          };

          if (existingIndex >= 0) {
            const updated = [...prev];
            updated[existingIndex] = newVessel;
            return updated;
          }
          return [...prev, newVessel];
        });
      }
    });

    // Listen for vessel messages
    newSocket.on("vessel_message", (data) => {
      console.log("💬 Received vessel message:", data);
      setMessages((prev) => ({
        ...prev,
        [data.from]: [
          ...(prev[data.from] || []),
          {
            type: "received",
            text: data.text,
            time: data.time,
          },
        ],
      }));
    });

    setSocket(newSocket);

    return () => {
      console.log("🔌 Base Station: Disconnecting WebSocket...");
      newSocket.disconnect();
    };
  }, []);

  // ==================== REST API FALLBACK ====================
  const fetchVessels = async () => {
    if (socketConnected) return; // Skip if WebSocket is active

    try {
      const response = await fetch(`${API_URL}/api/vessel/latest`);
      if (response.ok) {
        const data = await response.json();
        if (data && Object.keys(data).length > 0) {
          setBackendConnected(true);

          // Add vessel from REST API
          setVessels((prev) => {
            const newVessel = {
              id: data.id || "FV-REST",
              name: data.name || "REST Vessel",
              lat: data.lat || 10.0,
              lon: data.lon || 76.0,
              battery: data.battery || 50,
              speed: data.speed || 0,
              heading: data.heading || 0,
              image: "🚢",
            };

            const existingIndex = prev.findIndex((v) => v.id === newVessel.id);
            if (existingIndex >= 0) {
              const updated = [...prev];
              updated[existingIndex] = newVessel;
              return updated;
            }
            return [...prev, newVessel];
          });
        }
      } else {
        initializeFallbackData();
      }
    } catch (error) {
      console.error("❌ REST API Error:", error);
      initializeFallbackData();
    } finally {
      setLoading(false);
    }
  };

  const fetchWeather = async () => {
    try {
      const response = await fetch(`${API_URL}/api/weather`);
      if (response.ok) {
        const data = await response.json();
        setWeather(data);
      } else {
        initializeFallbackWeather();
      }
    } catch (error) {
      initializeFallbackWeather();
    }
  };

  const initializeFallbackData = () => {
    if (vessels.length > 0) return; // Don't override if we have vessels

    const initialVessels = [
      {
        id: "FV-001",
        name: "Mahi Maatha",
        lat: 10.05,
        lon: 76.2,
        battery: 85,
        speed: 8,
        heading: 45,
        image: "🚢",
      },
      {
        id: "FV-002",
        name: "Samudra Sena",
        lat: 10.12,
        lon: 76.15,
        battery: 32,
        speed: 12,
        heading: 120,
        image: "⛵",
      },
    ];

    setVessels(initialVessels);
    setMessages(
      initialVessels.reduce((acc, v) => ({ ...acc, [v.id]: [] }), {})
    );

    const trackMap = {};
    initialVessels.forEach((v) => {
      trackMap[v.id] = [{ lat: v.lat, lon: v.lon }];
    });
    setVesselTracks(trackMap);
    setBackendConnected(false);
  };

  const initializeFallbackWeather = () => {
    setWeather({
      temp: 28,
      humidity: 75,
      windSpeed: 12,
      windDir: "SW",
      waveHeight: 1.5,
      forecast: [
        { day: "Tomorrow", high: 29, low: 25, condition: "Sunny", rain: 10 },
        { day: "Thu", high: 28, low: 24, condition: "Partly Cloudy", rain: 20 },
        { day: "Fri", high: 27, low: 23, condition: "Rainy", rain: 70 },
        { day: "Sat", high: 26, low: 22, condition: "Monsoon", rain: 90 },
      ],
    });
  };

  useEffect(() => {
    fetchVessels();
    fetchWeather();

    const interval = setInterval(() => {
      if (!socketConnected) {
        fetchVessels();
        fetchWeather();
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [socketConnected]);

  const sendMessage = (vesselId) => {
    if (!chatMessage.trim()) return;

    const msgTime = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

    setMessages((prev) => ({
      ...prev,
      [vesselId]: [
        ...(prev[vesselId] || []),
        {
          type: "sent",
          text: chatMessage,
          time: msgTime,
        },
      ],
    }));

    // Send via WebSocket if connected
    if (socket && socketConnected) {
      socket.emit("basestation_message", {
        to: vesselId,
        text: chatMessage,
        time: msgTime,
      });
    }

    setChatMessage("");
  };

  const calculateDistance = (lat, lon) => {
    const R = 3440.07;
    const dLat = ((lat - baseCoast.lat) * Math.PI) / 180;
    const dLon = ((lon - baseCoast.lon) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((baseCoast.lat * Math.PI) / 180) *
        Math.cos((lat * Math.PI) / 180) *
        Math.sin(dLon / 2) *
        Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return (R * c).toFixed(1);
  };

  // ... rest of the component logic remains the same ...
  // Just showing the key WebSocket integration parts

  if (loading) {
    return (
      <div
        style={{
          minHeight: "100vh",
          background: "linear-gradient(135deg, #0a0e27 0%, #16213e 100%)",
          color: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "20px",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              width: "50px",
              height: "50px",
              border: "4px solid #00d4ff",
              borderTopColor: "transparent",
              borderRadius: "50%",
              animation: "spin 1s linear infinite",
              margin: "0 auto 20px",
            }}
          />
          <p>Loading Samudra Rakshak Base Station...</p>
          <style>
            {`
              @keyframes spin {
                to { transform: rotate(360deg); }
              }
            `}
          </style>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(135deg, #0a0e27 0%, #16213e 100%)",
        color: "#fff",
        padding: "20px",
      }}
    >
      <div style={{ maxWidth: "1600px", margin: "0 auto" }}>
        {/* Header with Connection Status */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "20px",
          }}
        >
          <div>
            <h1
              style={{
                fontSize: "32px",
                fontWeight: "bold",
                color: "#00d4ff",
                margin: 0,
              }}
            >
              Samudra Rakshak - Base Station
            </h1>
            <p style={{ color: "#888", fontSize: "12px", margin: "5px 0 0 0" }}>
              Real-time Maritime Tracking
            </p>
          </div>

          {/* Connection Status Indicators */}
          <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
            <div
              style={{
                padding: "8px 12px",
                borderRadius: "6px",
                background: socketConnected
                  ? "rgba(74,222,128,0.2)"
                  : "rgba(239,68,68,0.2)",
                border: `1px solid ${socketConnected ? "#4ade80" : "#ef4444"}`,
                color: socketConnected ? "#4ade80" : "#ef4444",
                fontSize: "12px",
                fontWeight: "bold",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <div
                style={{
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  background: socketConnected ? "#4ade80" : "#ef4444",
                  animation: socketConnected ? "pulse 2s infinite" : "none",
                }}
              ></div>
              WebSocket: {socketConnected ? "Connected" : "Disconnected"}
            </div>

            <div
              style={{
                padding: "8px 12px",
                borderRadius: "6px",
                background: backendConnected
                  ? "rgba(74,222,128,0.2)"
                  : "rgba(239,68,68,0.2)",
                border: `1px solid ${backendConnected ? "#4ade80" : "#ef4444"}`,
                color: backendConnected ? "#4ade80" : "#ef4444",
                fontSize: "12px",
                fontWeight: "bold",
              }}
            >
              Backend: {backendConnected ? "Connected" : "Offline"}
            </div>
          </div>
        </div>

        {/* Show active vessels count */}
        <div
          style={{
            background: "rgba(6,182,212,0.2)",
            border: "1px solid #00d4ff",
            borderRadius: "8px",
            padding: "12px",
            marginBottom: "20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ color: "#00d4ff", fontWeight: "bold" }}>
            📡 Active Vessels: {vessels.length}
          </span>
          <span style={{ color: "#888", fontSize: "12px" }}>
            Last update: {new Date().toLocaleTimeString()}
          </span>
        </div>

        {/* Pulse animation CSS */}
        <style>{`
          @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
          }
        `}</style>

        {/* Rest of your dashboard UI remains the same... */}
        {/* Vessels display, weather, chat, etc. */}
      </div>
    </div>
  );
}
