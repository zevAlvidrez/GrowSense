"""
Gemini AI client for generating plant care advice.

This module provides a placeholder function for calling Google's Gemini API.
The actual Gemini API integration should be implemented by adding the API call
in the get_gemini_advice() function below.

SETUP INSTRUCTIONS:
1. Install the Gemini SDK: pip install google-generativeai
2. Get a Gemini API key from: https://makersuite.google.com/app/apikey
3. Set environment variable: GEMINI_API_KEY=your-api-key-here
4. Implement the get_gemini_advice() function below
"""

import os
import json


def get_gemini_advice(formatted_data):
    """
    Get plant care advice from Gemini AI based on user's sensor data.
    
    THIS IS A PLACEHOLDER - IMPLEMENT THE ACTUAL GEMINI API CALL HERE.
    
    Args:
        formatted_data: Dictionary containing formatted device data, structured as:
            {
                "user_id": "user123",
                "device_count": 3,
                "devices": [
                    {
                        "device_id": "esp32_001",
                        "name": "Kitchen Sensor",
                        "last_seen": "2024-11-13T12:00:00Z",
                        "recent_readings": [
                            {
                                "timestamp": "2024-11-13T12:00:00Z",
                                "temperature": 23.5,
                                "humidity": 60.0,
                                "light": 450,
                                "soil_moisture": 45.0
                            },
                            # ... more readings
                        ],
                        "summary": {
                            "reading_count": 50,
                            "avg_temperature": 23.2,
                            "avg_humidity": 58.5,
                            "avg_light": 420,
                            "avg_soil_moisture": 45.0,
                            "min_temperature": 20.0,
                            "max_temperature": 26.0,
                            # ... more stats
                        }
                    },
                    # ... more devices
                ],
                "overall_summary": {
                    "total_readings": 150,
                    "time_range": "last_24_hours",
                    "avg_temperature": 23.1,
                    "avg_humidity": 58.0,
                    # ... more overall stats
                }
            }
    
    Returns:
        dict: Structured advice in the following format:
            {
                "overall_advice": "Your plants are generally healthy. Consider...",
                "device_advice": [
                    {
                        "device_id": "esp32_001",
                        "device_name": "Kitchen Sensor",
                        "advice": "Temperature is slightly high for optimal growth...",
                        "priority": "medium",  # One of: "low", "medium", "high", "urgent"
                        "recommendations": [
                            "Move plant to shadier location",
                            "Increase watering frequency to 2x per week"
                        ]
                    },
                    # ... more device-specific advice
                ],
                "insights": [
                    "Your humidity levels are consistent across all devices",
                    "Soil moisture is trending downward - consider watering soon"
                ]
            }
    
    IMPLEMENTATION NOTES:
    - Use google.generativeai library to call Gemini API
    - Construct a prompt that includes:
      * Summary of all devices and their current conditions
      * Recent sensor readings for context
      * Request for actionable advice
    - Parse Gemini's response into the structured format above
    - Handle errors gracefully (return default advice if API fails)
    """
    
    # TODO: IMPLEMENT GEMINI API CALL HERE
    # 
    # Example structure:
    # import google.generativeai as genai
    # 
    # genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
    # model = genai.GenerativeModel('gemini-pro')
    # 
    # prompt = construct_prompt(formatted_data)
    # response = model.generate_content(prompt)
    # 
    # advice = parse_gemini_response(response.text)
    # return advice
    
    # PLACEHOLDER: Return mock advice for testing
    # Remove this once Gemini API is implemented
    device_count = formatted_data.get('device_count', 0)
    
    if device_count == 0:
        return {
            "overall_advice": "No devices found. Please register a device to receive plant care advice.",
            "device_advice": [],
            "insights": []
        }
    
    # Mock response structure (replace with actual Gemini API call)
    mock_advice = {
        "overall_advice": "Your plants are generally healthy. Monitor soil moisture levels as they may need watering soon.",
        "device_advice": [],
        "insights": [
            "Sensor data is being collected successfully",
            "Replace this with actual Gemini API integration"
        ]
    }
    
    # Generate mock device-specific advice
    for device in formatted_data.get('devices', []):
        device_advice = {
            "device_id": device['device_id'],
            "device_name": device.get('name', device['device_id']),
            "advice": f"Device {device.get('name', device['device_id'])} is functioning normally. Temperature and humidity are within acceptable ranges.",
            "priority": "low",
            "recommendations": [
                "Continue monitoring sensor readings",
                "Check soil moisture if readings drop below 30%"
            ]
        }
        mock_advice["device_advice"].append(device_advice)
    
    return mock_advice


def construct_prompt(formatted_data):
    """
    Construct a prompt for Gemini based on formatted sensor data.
    
    This is a helper function you can use to build the prompt for Gemini.
    Customize the prompt structure based on your needs.
    
    Args:
        formatted_data: The formatted data dictionary (same as get_gemini_advice input)
        
    Returns:
        str: Formatted prompt string for Gemini
    """
    # TODO: Implement prompt construction
    # This should create a clear, structured prompt that:
    # 1. Describes the user's setup (number of devices, plant types if known)
    # 2. Provides recent sensor readings
    # 3. Includes summary statistics
    # 4. Asks for specific, actionable advice
    
    prompt = f"""
    You are a plant care expert. Analyze the following sensor data from {formatted_data.get('device_count', 0)} plant monitoring devices:
    
    {json.dumps(formatted_data, indent=2)}
    
    Please provide:
    1. Overall assessment of plant health
    2. Device-specific recommendations
    3. Actionable insights
    
    Format your response as JSON matching the expected output structure.
    """
    
    return prompt


def parse_gemini_response(response_text):
    """
    Parse Gemini's text response into structured advice format.
    
    This helper function can be used to extract structured data from Gemini's response.
    You may need to adjust this based on how Gemini formats its responses.
    
    Args:
        response_text: Raw text response from Gemini API
        
    Returns:
        dict: Structured advice dictionary
    """
    # TODO: Implement response parsing
    # Gemini may return JSON, markdown, or plain text
    # Parse it into the expected structure:
    # {
    #   "overall_advice": "...",
    #   "device_advice": [...],
    #   "insights": [...]
    # }
    
    # If Gemini returns JSON, parse it:
    # try:
    #     return json.loads(response_text)
    # except:
    #     # If not JSON, parse text format
    #     ...
    
    return {}

