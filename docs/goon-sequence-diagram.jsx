import React, { useState } from "react";

const flows = {
  sms_simple: {
    title: "Flow 1: Simple Question (No Call Needed)",
    example: '"What are the hours for Blue Bottle Coffee?"',
    steps: [
      { from: 0, to: 1, label: "SMS: 'What are the hours...'" },
      { from: 1, to: 2, label: "POST /sms/webhook" },
      { from: 2, to: 3, label: "check_cache('Blue Bottle hours')" },
      { from: 3, to: 2, label: "MISS (not cached)" },
      { from: 2, to: 4, label: "search_places('Blue Bottle Coffee')" },
      { from: 4, to: 5, label: "Places API v2 lookup" },
      { from: 5, to: 4, label: "hours, address, phone, rating" },
      { from: 4, to: 2, label: "PlaceResult{hours: '6am-7pm'}" },
      { from: 2, to: 3, label: "store_fact('Blue Bottle', hours, 7d expiry)" },
      { from: 2, to: 6, label: "Claude formats SMS response" },
      { from: 6, to: 1, label: "Twilio send_sms()" },
      { from: 1, to: 0, label: "SMS: 'Blue Bottle is open 6am-7pm today'" },
    ],
  },
  sms_call: {
    title: "Flow 2: Call Required (Reservation)",
    example: '"Make a reservation for 2 at Flour+Water tonight at 7pm"',
    steps: [
      { from: 0, to: 1, label: "SMS: 'Make a reservation...'" },
      { from: 1, to: 2, label: "POST /sms/webhook" },
      { from: 2, to: 3, label: "check_cache('Flour+Water reservations')" },
      { from: 3, to: 2, label: "MISS" },
      { from: 2, to: 4, label: "search_places('Flour+Water SF')" },
      { from: 4, to: 5, label: "Places API lookup" },
      { from: 5, to: 4, label: "phone: +1415xxx, open_now: true" },
      { from: 4, to: 2, label: "PlaceResult with phone number" },
      { from: 2, to: 2, label: "pre_call_check: open? phone reliable?" },
      { from: 2, to: 6, label: "Claude decides: need to call" },
      { from: 6, to: 1, label: "SMS: 'Calling Flour+Water now. Back in a few.'" },
      { from: 1, to: 0, label: "SMS: interim status" },
      { from: 2, to: 7, label: "initiate_outbound_call()" },
      { from: 7, to: 8, label: "POST /call (Vapi API)" },
      { from: 8, to: 9, label: "Vapi calls restaurant" },
      { from: 9, to: 8, label: "Restaurant answers" },
      { from: 8, to: 9, label: "'Hi, I'd like a table for 2 at 7pm tonight'" },
      { from: 9, to: 8, label: "'Sure, name?' → 'Riley' → 'Confirmed!'" },
      { from: 8, to: 7, label: "POST /vapi/events (call ended)" },
      { from: 7, to: 2, label: "transcript + outcome: success" },
      { from: 2, to: 3, label: "store_fact('Flour+Water', reservation_info)" },
      { from: 2, to: 6, label: "Claude formats result" },
      { from: 6, to: 1, label: "Twilio send_sms()" },
      { from: 1, to: 0, label: "SMS: 'Reserved! Table for 2 at 7pm, under Riley'" },
    ],
  },
  unregistered: {
    title: "Flow 3: Unregistered User",
    example: "Random person texts your Goon number",
    steps: [
      { from: 0, to: 1, label: "SMS: 'Hey what is this'" },
      { from: 1, to: 2, label: "POST /sms/webhook" },
      { from: 2, to: 10, label: "get_user(phone) → None" },
      { from: 10, to: 2, label: "User not found" },
      { from: 2, to: 11, label: "handle_unregistered(phone, message)" },
      { from: 11, to: 3, label: "log to unregistered_attempts" },
      { from: 11, to: 1, label: "Teaser SMS: 'This is Goon...sign up at getgoon.com'" },
      { from: 1, to: 0, label: "SMS: teaser response" },
    ],
  },
  voice_inbound: {
    title: "Flow 4: Voice Inbound (User Calls Goon)",
    example: "You call the Goon number instead of texting",
    steps: [
      { from: 0, to: 1, label: "📞 Calls Goon number" },
      { from: 1, to: 2, label: "POST /voice/inbound (Twilio webhook)" },
      { from: 2, to: 8, label: "Route to Vapi inbound assistant" },
      { from: 8, to: 0, label: "'Hey! What can I help with?'" },
      { from: 0, to: 8, label: "'What time does Tartine close?'" },
      { from: 8, to: 4, label: "Tool call: search_places('Tartine')" },
      { from: 4, to: 5, label: "Places API" },
      { from: 5, to: 4, label: "closes at 5pm" },
      { from: 4, to: 8, label: "PlaceResult" },
      { from: 8, to: 0, label: "'Tartine closes at 5pm today'" },
    ],
  },
};

const actors = [
  { id: 0, label: "You", sub: "(Phone)", color: "#3b82f6", icon: "📱" },
  { id: 1, label: "Twilio", sub: "(SMS/Voice)", color: "#ef4444", icon: "📡" },
  { id: 2, label: "Orchestrator", sub: "(The Brain)", color: "#8b5cf6", icon: "🧠" },
  { id: 3, label: "Fact Cache", sub: "(SQLite)", color: "#f59e0b", icon: "💾" },
  { id: 4, label: "Places", sub: "(Google)", color: "#10b981", icon: "📍" },
  { id: 5, label: "Google API", sub: "", color: "#6b7280", icon: "☁️" },
  { id: 6, label: "Claude LLM", sub: "(Sonnet 4.5)", color: "#ec4899", icon: "🤖" },
  { id: 7, label: "Calls Service", sub: "(calls.py)", color: "#f97316", icon: "📞" },
  { id: 8, label: "Vapi", sub: "(Voice AI)", color: "#14b8a6", icon: "🗣️" },
  { id: 9, label: "Restaurant", sub: "(Business)", color: "#78716c", icon: "🍽️" },
  { id: 10, label: "Auth", sub: "(auth.py)", color: "#64748b", icon: "🔐" },
  { id: 11, label: "Leads", sub: "(leads.py)", color: "#a855f7", icon: "📊" },
];

export default function GoonSequenceDiagram() {
  const [activeFlow, setActiveFlow] = useState("sms_simple");
  const [currentStep, setCurrentStep] = useState(-1);
  const [isPlaying, setIsPlaying] = useState(false);

  const flow = flows[activeFlow];

  const usedActorIds = [...new Set(flow.steps.flatMap((s) => [s.from, s.to]))];
  const usedActors = actors.filter((a) => usedActorIds.includes(a.id));

  const colWidth = 140;
  const totalWidth = usedActors.length * colWidth;
  const stepHeight = 48;
  const headerHeight = 100;
  const totalHeight = headerHeight + flow.steps.length * stepHeight + 60;

  const getX = (actorId) => {
    const idx = usedActors.findIndex((a) => a.id === actorId);
    return idx * colWidth + colWidth / 2;
  };

  const playAnimation = () => {
    setCurrentStep(-1);
    setIsPlaying(true);
    let step = 0;
    const interval = setInterval(() => {
      if (step >= flow.steps.length) {
        clearInterval(interval);
        setIsPlaying(false);
        return;
      }
      setCurrentStep(step);
      step++;
    }, 800);
  };

  const reset = () => {
    setCurrentStep(-1);
    setIsPlaying(false);
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white p-4">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-1">Goon — System Flow Diagrams</h1>
        <p className="text-gray-400 text-sm mb-6">
          How SMS, voice calls, and AI orchestration work together
        </p>

        <div className="flex flex-wrap gap-2 mb-6">
          {Object.entries(flows).map(([key, f]) => (
            <button
              key={key}
              onClick={() => {
                setActiveFlow(key);
                setCurrentStep(-1);
                setIsPlaying(false);
              }}
              className={`px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                activeFlow === key
                  ? "bg-blue-600 text-white"
                  : "bg-gray-800 text-gray-300 hover:bg-gray-700"
              }`}
            >
              {f.title.split(":")[0]}
            </button>
          ))}
        </div>

        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 mb-4">
          <div className="flex items-center justify-between mb-2">
            <div>
              <h2 className="text-lg font-semibold">{flow.title}</h2>
              <p className="text-gray-400 text-sm italic">{flow.example}</p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={playAnimation}
                disabled={isPlaying}
                className="px-3 py-1.5 bg-green-600 hover:bg-green-500 disabled:bg-gray-700 disabled:text-gray-500 rounded text-sm font-medium transition-colors"
              >
                ▶ Play
              </button>
              <button
                onClick={() => setCurrentStep(flow.steps.length - 1)}
                className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium transition-colors"
              >
                Show All
              </button>
              <button
                onClick={reset}
                className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium transition-colors"
              >
                Reset
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <svg
              width={Math.max(totalWidth, 700)}
              height={totalHeight}
              className="mx-auto"
            >
              {usedActors.map((actor, i) => {
                const x = i * colWidth + colWidth / 2;
                const isActive =
                  currentStep >= 0 &&
                  (flow.steps[currentStep]?.from === actor.id ||
                    flow.steps[currentStep]?.to === actor.id);
                return (
                  <g key={actor.id}>
                    <rect
                      x={x - 52}
                      y={10}
                      width={104}
                      height={60}
                      rx={8}
                      fill={isActive ? actor.color + "33" : "#1f2937"}
                      stroke={isActive ? actor.color : "#374151"}
                      strokeWidth={isActive ? 2 : 1}
                    />
                    <text
                      x={x}
                      y={32}
                      textAnchor="middle"
                      className="text-lg"
                      fill="white"
                    >
                      {actor.icon}
                    </text>
                    <text
                      x={x}
                      y={50}
                      textAnchor="middle"
                      fontSize={11}
                      fontWeight="bold"
                      fill="white"
                    >
                      {actor.label}
                    </text>
                    <text
                      x={x}
                      y={63}
                      textAnchor="middle"
                      fontSize={9}
                      fill="#9ca3af"
                    >
                      {actor.sub}
                    </text>

                    <line
                      x1={x}
                      y1={75}
                      x2={x}
                      y2={totalHeight - 20}
                      stroke="#374151"
                      strokeWidth={1}
                      strokeDasharray="4 4"
                    />
                  </g>
                );
              })}

              {flow.steps.map((step, i) => {
                if (i > currentStep) return null;

                const fromX = getX(step.from);
                const toX = getX(step.to);
                const y = headerHeight + i * stepHeight;
                const isCurrentStep = i === currentStep;
                const isSelfCall = step.from === step.to;

                const fromActor = actors.find((a) => a.id === step.from);
                const arrowColor = isCurrentStep
                  ? fromActor.color
                  : fromActor.color + "88";

                if (isSelfCall) {
                  const loopSize = 20;
                  return (
                    <g key={i} opacity={isCurrentStep ? 1 : 0.7}>
                      <path
                        d={`M ${fromX} ${y} 
                            C ${fromX + loopSize * 2} ${y}, 
                              ${fromX + loopSize * 2} ${y + loopSize}, 
                              ${fromX} ${y + loopSize}`}
                        fill="none"
                        stroke={arrowColor}
                        strokeWidth={isCurrentStep ? 2 : 1.5}
                      />
                      <polygon
                        points={`${fromX},${y + loopSize} ${fromX + 5},${y + loopSize - 5} ${fromX - 5},${y + loopSize - 5}`}
                        fill={arrowColor}
                      />
                      <rect
                        x={fromX + loopSize * 2 + 4}
                        y={y - 2}
                        width={step.label.length * 5.5 + 12}
                        height={18}
                        rx={3}
                        fill="#111827"
                        stroke={arrowColor}
                        strokeWidth={0.5}
                      />
                      <text
                        x={fromX + loopSize * 2 + 10}
                        y={y + 11}
                        fontSize={9}
                        fill={isCurrentStep ? "#f3f4f6" : "#9ca3af"}
                      >
                        {step.label}
                      </text>
                    </g>
                  );
                }

                const direction = toX > fromX ? 1 : -1;
                const arrowStart = fromX + direction * 8;
                const arrowEnd = toX - direction * 8;
                const midX = (arrowStart + arrowEnd) / 2;

                return (
                  <g key={i} opacity={isCurrentStep ? 1 : 0.7}>
                    <line
                      x1={arrowStart}
                      y1={y}
                      x2={arrowEnd}
                      y2={y}
                      stroke={arrowColor}
                      strokeWidth={isCurrentStep ? 2 : 1.5}
                    />
                    <polygon
                      points={`${arrowEnd},${y} ${arrowEnd - direction * 7},${y - 4} ${arrowEnd - direction * 7},${y + 4}`}
                      fill={arrowColor}
                    />

                    {(() => {
                      const maxLabelWidth =
                        Math.abs(arrowEnd - arrowStart) - 10;
                      const truncated =
                        step.label.length * 5.5 > maxLabelWidth
                          ? step.label.substring(
                              0,
                              Math.floor(maxLabelWidth / 5.5) - 2
                            ) + "…"
                          : step.label;
                      const labelWidth = truncated.length * 5.5 + 10;
                      return (
                        <>
                          <rect
                            x={midX - labelWidth / 2}
                            y={y - 16}
                            width={labelWidth}
                            height={14}
                            rx={3}
                            fill="#111827ee"
                          />
                          <text
                            x={midX}
                            y={y - 6}
                            textAnchor="middle"
                            fontSize={9}
                            fill={isCurrentStep ? "#f3f4f6" : "#9ca3af"}
                          >
                            {truncated}
                          </text>
                        </>
                      );
                    })()}
                  </g>
                );
              })}
            </svg>
          </div>
        </div>

        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">
            Resolution Ladder (cheapest → most expensive)
          </h3>
          <div className="flex flex-wrap gap-2">
            {[
              {
                step: "1. Cache",
                cost: "~free",
                time: "<50ms",
                color: "#f59e0b",
              },
              {
                step: "2. Google Places",
                cost: "~$0.002",
                time: "~200ms",
                color: "#10b981",
              },
              {
                step: "3. Web Search",
                cost: "~$0.01",
                time: "~1-3s",
                color: "#3b82f6",
              },
              {
                step: "4. Pre-call Check",
                cost: "free",
                time: "<200ms",
                color: "#64748b",
              },
              {
                step: "5. Voice Call",
                cost: "~$0.10-0.20",
                time: "~2-5min",
                color: "#ef4444",
              },
            ].map((item) => (
              <div
                key={item.step}
                className="flex items-center gap-2 bg-gray-800 rounded px-3 py-2"
              >
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: item.color }}
                />
                <span className="text-sm font-medium">{item.step}</span>
                <span className="text-xs text-gray-500">
                  {item.cost} · {item.time}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
