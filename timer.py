import time

def perform_action(value):
    print(f"Performing action for value: {value}")

def timer_with_events(events, player_time, sync_offset=0):
    start_time = time.time()  # Record the start time in seconds

    for event in events:
        start_ms = event['start'] * 1000  # Convert start time to milliseconds
        end_ms = event['end'] * 1000      # Convert end time to milliseconds
        value = event['value']

        # Adjust start and end times with player_time and sync_offset
        adjusted_start = start_ms + player_time + sync_offset
        adjusted_end = end_ms + player_time + sync_offset

        # Wait until the current time is equal to or greater than the adjusted start time
        while (time.time() - start_time) * 1000 < adjusted_start:
            time.sleep(0.001)  # Sleep for 1 millisecond to avoid busy waiting

        # Perform the action
        perform_action(value)

        # Calculate remaining time and sleep for that duration
        remaining_time = adjusted_end - adjusted_start
        time.sleep(remaining_time / 1000.0)  # Sleep for the remaining time in seconds

# Example usage
events = [
    {"start": 0.01, "end": 0.8, "value": "A"},
    {"start": 0.8, "end": 1.5, "value": "B"},
    {"start": 1.5, "end": 3.7, "value": "D"}
]

# Assume player_time is 2000 milliseconds (2 seconds)
player_time = 5000

# Synchronization offset of 100 milliseconds
sync_offset = 100

timer_with_events(events, player_time, sync_offset)
