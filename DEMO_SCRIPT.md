# Demo script — 4 minutes

Before going on stage: `./start.sh`, open http://localhost:8000, press **Reset day**, browser
full-screen (F11), zoom 90–100%. Keep the backup video open in another tab.

| Time | Screen | Say | Do |
|---|---|---|---|
| 0:00–0:30 | Command Centre | "A sandstorm hits a Gulf hub at 2 pm. One runway closes, the other drops to 12 movements an hour. Today, recovering means a room full of people and phone calls, and aircraft running low on fuel in the holding stack." | Point at 36 flights, 2/2 runways. |
| 0:30–1:00 | Command Centre | "This is SkyOps Twin: a live digital twin plus seven AI agents that recover the operation, and a human who stays in charge." | Click **Inject OPERATION SANDSTORM** (or hand the mouse to a judge). |
| 1:00–1:45 | Command Centre → Agent Control Room | "Watch the agents. Weather publishes restrictions. Runway predicts two diversions. Flight, Gate and Ground work in parallel." Point at the holding stack filling up. | Switch to **Agent Control Room**. Point at the negotiation graph and plan versions. |
| 1:45–2:30 | Agent Control Room | "Here's the part a chatbot can't do: they disagree. Gate tells Flight its sequence lands aircraft before a gate is free. Ground withdraws its own crew-pooling idea because the simulation proved it costs more than it saves. Every tool call is real; click one." | Expand a tool call (JSON). |
| 2:30–3:10 | Recovery & Analytics | "The Recovery agent searched 72 plans, each simulated and validated. An independent reviewer disagrees on a trade-off, so it's escalated to the controller, not decided by AI." | Point at the metric cards, the amber disagreement box and the validation checklist. |
| 3:10–3:45 | Recovery → Command Centre | "I approve." | Type a note, click **Approve plan**. The side-by-side replay starts. |
| 3:45–4:00 | Side-by-side | "Same storm, same airport. Left: two diversions, 4,918 passenger-delay hours. Right: zero diversions, 1,970. Every number computed by the engine, every plan checked against nine families of hard constraints." | Let the replay run. |

## Round 2 (Adapt and Test)
Ask the judge for an event and type it in **Judge's event**: e.g. "Debris on 30L, closed 45 minutes
at 14:40", "PG961 inbound 50 minutes late", "two ground crews off sick", "gate A2 jet bridge failure".
Or paste a METAR into **Live weather feed**.

## Likely judge questions

- **Is this just a chatbot?** No. Each agent has its own tools and constraints and returns structured output. They raise conflicts, re-plan, and withdraw proposals based on simulation evidence. The feed is the backend's real message log.
- **Can the AI make an unsafe decision?** Models can only choose levers; they never write state. Every plan is re-validated by deterministic code, and a human approves.
- **What if the AI API fails?** Each agent falls back to its deterministic policy; the header shows the mode. The demo runs fully offline.
- **Are the numbers real?** They are computed by the simulation on a synthetic airport with labelled assumptions, and they are reproducible (seeded).
- **How would this connect to a real airport?** Adapters: METAR (working), AODB schedule, A-CDM TSAT/TTOT messages, resource management.
- **Why do 8 flights get worse?** The plan protects arrivals near their fuel limit and high-connection flights. The reviewer lists exactly which flights pay for it, so the controller sees the trade-off.

## If something breaks
- UI frozen → refresh the page (state is server-side).
- Backend down → restart `./start.sh`, press Reset day.
- Anything else → play the backup video and keep talking.
