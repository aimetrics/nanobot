# Heartbeat Tasks

This file is checked every 30 minutes by your nanobot agent.
Add tasks below that you want the agent to work on periodically.

If this file has no tasks (only headers and comments), the agent will skip the heartbeat.

## Active Tasks

<!-- Add your periodic tasks below this line -->

- Use the `calendar` tool to check today's calendar events (`action="today"`).
- If there are events within the next 2 hours, send a concise reminder with time and title.
- If calendar has no urgent action, respond with HEARTBEAT_OK.

## Completed

<!-- Move completed tasks here or delete them -->

