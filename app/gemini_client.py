"""
Gemini AI client for generating plant care advice.

This module provides functions for calling Google's Gemini API to generate
plant care advice based on sensor data from user's devices.

Supports two output formats:
1. API format (for routes.py): overall_advice, device_advice, insights
2. Analysis format (for CLI/standalone use): ideal_thresholds, plant_health_score, status_summary, trend_analysis, recommendations
"""

import os
import json
import time
import argparse
import google.generativeai as genai
import google.api_core.exceptions
from firebase_admin import firestore

# Handle imports for both module and standalone script usage
try:
    from app.firebase_client import get_firestore, prepare_data_for_gemini
except ImportError:
    # When running as standalone script
    from firebase_client import get_firestore, prepare_data_for_gemini

# Initialize Gemini API
try:
    api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set")
    
    genai.configure(api_key=api_key)
    
    # Find a suitable model dynamically, prioritizing Flash models
    model_name = None
    flash_model = None
    pro_model = None
    
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            if 'gemini-1.5-flash-latest' in m.name:
                flash_model = m.name
                break
            elif 'flash' in m.name and not flash_model:
                flash_model = m.name
            elif 'pro' in m.name and not pro_model:
                pro_model = m.name
    
    model_name = flash_model if flash_model else pro_model
    
    if model_name:
        gemini_model = genai.GenerativeModel(model_name)
    else:
        raise ValueError("Could not find a suitable Gemini model")
        
except Exception as e:
    print(f"Warning: Gemini API initialization failed: {e}")
    gemini_model = None


def load_user_analysis_history(user_id):
    """
    Load previous analysis history for a user from Firestore.
    
    Args:
        user_id: Firebase user ID
    
    Returns:
        list: Previous analyses for the user
    """
    try:
        db = get_firestore()
        
        # Get last 10 analyses for this user ordered by timestamp
        history_ref = db.collection('users').document(user_id).collection('analysis_history')
        query = history_ref.order_by('analysis_timestamp', direction='DESCENDING').limit(10)
        
        docs = list(query.stream())
        
        history = []
        for doc in docs:
            data = doc.to_dict()
            # Convert Firestore timestamp to string for JSON serialization
            if 'analysis_timestamp' in data and hasattr(data['analysis_timestamp'], 'strftime'):
                data['analysis_timestamp'] = data['analysis_timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            history.append(data)
        
        # Reverse to get chronological order (oldest to newest)
        history.reverse()
        
        return history
        
    except Exception as e:
        print(f"Warning: Could not load analysis history: {e}")
        return []


def get_gemini_advice(formatted_data, output_format='api'):
    """
    Get plant care advice from Gemini AI based on user's sensor data.
    
    Args:
        formatted_data: Dictionary containing formatted device data from prepare_data_for_gemini()
        output_format: 'api' (default) or 'analysis'
            - 'api': Returns format for routes.py (overall_advice, device_advice, insights)
            - 'analysis': Returns format for CLI/standalone use (ideal_thresholds, plant_health_score, etc.)
    
    Returns:
        dict: Structured advice in the requested format
    """
    if not gemini_model:
        return {
            "overall_advice": "Gemini API is not configured. Please set GOOGLE_API_KEY environment variable.",
            "device_advice": [],
            "insights": []
        }
    
    device_count = formatted_data.get('device_count', 0)
    
    if device_count == 0:
        return {
            "overall_advice": "No devices found. Please register a device to receive plant care advice.",
            "device_advice": [],
            "insights": []
        }
    
    # Load previous analysis history for context
    user_id = formatted_data.get('user_id')
    analysis_history = []
    if user_id:
        analysis_history = load_user_analysis_history(user_id)
    
    # Construct prompt based on output format
    if output_format == 'analysis':
        prompt = construct_analysis_prompt(formatted_data, analysis_history)
    else:
        prompt = construct_prompt(formatted_data, analysis_history)
    
    # Call Gemini API with retry logic
    retries = 3
    delay = 5
    
    for i in range(retries):
        try:
            response = gemini_model.generate_content(prompt)
            cleaned_response = response.text.strip().replace("``````", "").replace("```json", "").replace("```", "")
            advice = parse_gemini_response(cleaned_response, output_format)
            
            # Validate and ensure proper structure
            if not isinstance(advice, dict):
                raise ValueError("Response is not a dictionary")
            
            # Ensure required fields exist based on format
            if output_format == 'analysis':
                if 'ideal_thresholds' not in advice:
                    advice['ideal_thresholds'] = {"soil_moisture_percent": "40-60%", "soil_ph": "6.0-7.0"}
                if 'plant_health_score' not in advice:
                    advice['plant_health_score'] = 5
                if 'status_summary' not in advice:
                    advice['status_summary'] = "Analysis completed."
                if 'trend_analysis' not in advice:
                    advice['trend_analysis'] = "Monitoring sensor data trends."
                if 'recommendations' not in advice:
                    advice['recommendations'] = []
            else:
                if 'overall_advice' not in advice:
                    advice['overall_advice'] = "Analysis completed. Please review device-specific recommendations."
                if 'device_advice' not in advice:
                    advice['device_advice'] = []
                if 'insights' not in advice:
                    advice['insights'] = []
            
            return advice
            
        except google.api_core.exceptions.ResourceExhausted as e:
            print(f"Gemini API quota exceeded. Waiting {delay} seconds before retrying... ({i + 1}/{retries})")
            time.sleep(delay)
            delay *= 2
        except json.JSONDecodeError as e:
            print(f"Error parsing Gemini response as JSON: {e}")
            print(f"Response was: {response.text[:500]}")
            if i == retries - 1:
                # Last retry failed, return default advice
                return get_default_advice(formatted_data, output_format)
        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            if i == retries - 1:
                # Last retry failed, return default advice
                return get_default_advice(formatted_data, output_format)
    
    return get_default_advice(formatted_data, output_format)


def get_default_advice(formatted_data, output_format='api'):
    """
    Return default advice structure when Gemini API fails.
    
    Args:
        formatted_data: Formatted device data
        output_format: 'api' (default) or 'analysis' - determines output structure
    
    Returns:
        dict: Default advice structure
    """
    device_count = formatted_data.get('device_count', 0)
    overall_summary = formatted_data.get('overall_summary', {})
    
    if output_format == 'analysis':
        # Return analysis format
        default_advice = {
            "ideal_thresholds": {
                "soil_moisture_percent": "40-60%",
                "soil_ph": "6.0-7.0"
            },
            "plant_health_score": 5,
            "status_summary": "Unable to generate AI analysis at this time. Please check your sensor readings manually.",
            "trend_analysis": f"Analyzing data from {device_count} device(s) with {overall_summary.get('total_readings', 0)} total readings.",
            "recommendations": [
                "Continue monitoring sensor readings",
                "Check sensor data regularly"
            ]
        }
        
        # Add device-specific recommendations
        for device in formatted_data.get('devices', []):
            summary = device.get('summary', {})
            if summary.get('avg_temperature'):
                default_advice['recommendations'].append(
                    f"Device {device.get('name', device['device_id'])}: Monitor temperature (avg: {summary.get('avg_temperature', 'N/A')}°C)"
                )
    else:
        # Return API format
        default_advice = {
            "overall_advice": "Unable to generate AI analysis at this time. Please check your sensor readings manually.",
            "device_advice": [],
            "insights": [
                f"Analyzing data from {device_count} device(s)",
                f"Total readings: {overall_summary.get('total_readings', 0)}"
            ]
        }
        
        # Generate basic device-specific advice
        for device in formatted_data.get('devices', []):
            summary = device.get('summary', {})
            device_advice = {
                "device_id": device['device_id'],
                "device_name": device.get('name', device['device_id']),
                "advice": f"Device is functioning. Average temperature: {summary.get('avg_temperature', 'N/A')}°C, Average humidity: {summary.get('avg_humidity', 'N/A')}%",
                "priority": "low",
                "recommendations": [
                    "Continue monitoring sensor readings",
                    "Check sensor data regularly"
                ]
            }
            default_advice["device_advice"].append(device_advice)
    
    return default_advice


def construct_prompt(formatted_data, analysis_history=None):
    """
    Construct a prompt for Gemini based on formatted sensor data.
    Uses a comprehensive prompt style for consistency.
    
    Args:
        formatted_data: The formatted data dictionary from prepare_data_for_gemini()
        analysis_history: Optional list of previous analyses for this user
        
    Returns:
        str: Formatted prompt string for Gemini
    """
    device_count = formatted_data.get('device_count', 0)
    devices = formatted_data.get('devices', [])
    overall_summary = formatted_data.get('overall_summary', {})
    
    # Build device information section
    device_info_section = f"""
    Device Information:
    - Number of devices: {device_count}
    - Total readings analyzed: {overall_summary.get('total_readings', 0)}
    - Time range: {overall_summary.get('time_range', 'unknown')}
    - Device names: {', '.join([d.get('name', d.get('device_id', 'unknown')) for d in devices])}
    """
    
    # Build device details section
    device_details_section = ""
    for device in devices:
        device_name = device.get('name', device.get('device_id', 'unknown'))
        summary = device.get('summary', {})
        recent_readings = device.get('recent_readings', [])
        
        device_details_section += f"""
    Device: {device_name} ({device.get('device_id', 'unknown')})
    - Recent readings count: {len(recent_readings)}
    - Average temperature: {summary.get('avg_temperature', 'N/A')}°C (range: {summary.get('min_temperature', 'N/A')} - {summary.get('max_temperature', 'N/A')}°C)
    - Average humidity: {summary.get('avg_humidity', 'N/A')}%
    - Average soil moisture: {summary.get('avg_soil_moisture', 'N/A')}%
    - Average light: {summary.get('avg_light', 'N/A')} lux
    - Recent readings: {json.dumps(recent_readings[:10], indent=2, default=str)}  # Show first 10 readings
    """
    
    # Analysis history section
    analysis_history_section = ""
    if analysis_history:
        analysis_history_section = f"""
    For additional long-term context, here is a log of previous analyses for this user.
    Use this to understand the plant's health trajectory and the effectiveness of past recommendations.
    {json.dumps(analysis_history, indent=2, default=str)}
    """
    
    prompt = f"""
    You are an expert botanist and data analyst. Based on the following sensor data from a user's plant monitoring devices, please provide a comprehensive analysis.

    {device_info_section}
    
    Overall Summary:
    - Average temperature across all devices: {overall_summary.get('avg_temperature', 'N/A')}°C
    - Average humidity across all devices: {overall_summary.get('avg_humidity', 'N/A')}%
    - Average soil moisture across all devices: {overall_summary.get('avg_soil_moisture', 'N/A')}%
    - Average light across all devices: {overall_summary.get('avg_light', 'N/A')} lux
    
    Device Details:
    {device_details_section}
    {analysis_history_section}
    
    Your primary task is to generate a comprehensive health assessment for the user's plants (like Fiddle Leaf Figs or similar houseplants).
    Your analysis should consider:
    - Trends from the sensor history across all devices
    - Your own previous analysis history for this user (if provided)
    - Any patterns or differences between devices if multiple devices are present
    - Summary statistics and recent readings for each device
    
    Your entire response MUST be a single, raw JSON object without any markdown formatting (no ``````).

    The JSON object must contain the following keys:
    - "overall_advice": A brief summary (2-3 sentences) of the overall plant health status across all devices.
    - "device_advice": An array of objects, one for each device, each containing:
        - "device_id": The device identifier
        - "device_name": The device name
        - "advice": A brief assessment (1-2 sentences) specific to this device
        - "priority": One of "low", "medium", "high", or "urgent" based on the severity of issues
        - "recommendations": An array of strings with specific, actionable recommendations for this device
    - "insights": An array of strings with key observations and patterns across all devices (2-5 insights).
    """
    
    return prompt


def construct_analysis_prompt(formatted_data, analysis_history=None):
    """
    Construct a prompt for Gemini analysis format (used by CLI/standalone analysis).
    Uses raw sensor readings for detailed analysis.
    
    Args:
        formatted_data: The formatted data dictionary from prepare_data_for_gemini()
        analysis_history: Optional list of previous analyses for this user
        
    Returns:
        str: Formatted prompt string for Gemini
    """
    device_count = formatted_data.get('device_count', 0)
    devices = formatted_data.get('devices', [])
    overall_summary = formatted_data.get('overall_summary', {})
    
    # Get latest reading from any device
    latest_reading = None
    historical_readings = []
    
    for device in devices:
        recent_readings = device.get('recent_readings', [])
        if recent_readings:
            # Sort by timestamp, get most recent
            sorted_readings = sorted(recent_readings, key=lambda x: x.get('timestamp', ''), reverse=True)
            if not latest_reading or (sorted_readings and sorted_readings[0].get('timestamp', '') > latest_reading.get('timestamp', '')):
                latest_reading = sorted_readings[0]
            historical_readings.extend(recent_readings)
    
    # Sort historical readings by timestamp
    historical_readings.sort(key=lambda x: x.get('timestamp', ''))
    
    device_info_section = f"""
    Device Information:
    - Number of devices: {device_count}
    - Total readings analyzed: {overall_summary.get('total_readings', 0)}
    - Device names: {', '.join([d.get('name', d.get('device_id', 'unknown')) for d in devices])}
    """
    
    analysis_history_section = ""
    if analysis_history:
        analysis_history_section = f"""
    For additional long-term context, here is a log of your own previous analyses for this user. 
    Use this to understand the plant's health trajectory and the effectiveness of past recommendations.
    {json.dumps(analysis_history, indent=2, default=str)}
    """
    
    prompt = f"""
    You are an expert botanist and data analyst. Based on the following sensor data from a user's plant monitoring devices, please provide a comprehensive analysis.

    {device_info_section}
    
    This is the most recent sensor reading (from any of the user's devices):
    {json.dumps(latest_reading, indent=2, default=str) if latest_reading else "No recent readings available"}

    For context, here is a history of sensor readings from all of the user's devices:
    {json.dumps(historical_readings, indent=2, default=str)}
    {analysis_history_section}
    
    Your primary task is to generate a comprehensive health assessment for the user's plants (like Fiddle Leaf Figs or similar houseplants).
    Your analysis should consider:
    - Trends from the sensor history across all devices
    - Your own previous analysis history for this user
    - Any patterns or differences between devices if multiple devices are present
    
    Your entire response MUST be a single, raw JSON object without any markdown formatting (no ``````).

    The JSON object must contain the following keys:
    - "ideal_thresholds": An object with "soil_moisture_percent" (ideal range) and "soil_ph" (ideal range).
    - "plant_health_score": A numerical score from 0 (very poor) to 10 (excellent).
    - "status_summary": A brief, one-sentence summary of the plant's current condition.
    - "trend_analysis": A new, brief summary (1-2 sentences) of any notable trends in the historical data across all devices.
    - "recommendations": An array of strings with specific, actionable recommendations.
    """
    
    return prompt


def parse_gemini_response(response_text, output_format='api'):
    """
    Parse Gemini's text response into structured advice format.
    
    Args:
        response_text: Raw text response from Gemini API
        output_format: 'api' (default) or 'analysis' - determines expected structure
    
    Returns:
        dict: Structured advice dictionary
    """
    if not response_text:
        return {}
    
    # Try to parse as JSON first
    try:
        # Remove any markdown code blocks if present
        cleaned = response_text.strip()
        if cleaned.startswith('```'):
            # Find the first newline after ```
            first_newline = cleaned.find('\n')
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        # Try to find JSON object
        start_idx = cleaned.find('{')
        end_idx = cleaned.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx:end_idx + 1]
        
        advice = json.loads(cleaned)
        
        # Validate structure
        if not isinstance(advice, dict):
            raise ValueError("Response is not a dictionary")
        
        # If output_format is 'analysis', ensure it has the right structure
        if output_format == 'analysis':
            # Convert API format to analysis format if needed
            if 'overall_advice' in advice and 'plant_health_score' not in advice:
                # This is API format, try to convert
                advice = convert_api_to_analysis_format(advice)
        
        return advice
        
    except json.JSONDecodeError as e:
        print(f"Warning: Could not parse Gemini response as JSON: {e}")
        print(f"Response text (first 500 chars): {response_text[:500]}")
        
        # Try to extract structured information from text format
        # This is a fallback if Gemini doesn't return pure JSON
        return parse_text_response(response_text)
    except Exception as e:
        print(f"Error parsing Gemini response: {e}")
        return {}


def convert_api_to_analysis_format(api_response):
    """
    Convert API format response to analysis format.
    This is a fallback if Gemini returns API format when analysis format was requested.
    """
    analysis_response = {
        "ideal_thresholds": {
            "soil_moisture_percent": "40-60%",
            "soil_ph": "6.0-7.0"
        },
        "plant_health_score": 7,  # Default middle score
        "status_summary": api_response.get('overall_advice', 'Analysis completed.'),
        "trend_analysis": " ".join(api_response.get('insights', [])[:2]) if api_response.get('insights') else "Monitoring sensor data.",
        "recommendations": []
    }
    
    # Extract recommendations from device_advice
    for device_advice in api_response.get('device_advice', []):
        analysis_response['recommendations'].extend(device_advice.get('recommendations', []))
    
    # If no recommendations, use insights
    if not analysis_response['recommendations']:
        analysis_response['recommendations'] = api_response.get('insights', [])
    
    return analysis_response


def parse_text_response(response_text):
    """
    Fallback parser for when Gemini returns text instead of JSON.
    Attempts to extract structured information from natural language.
    
    Args:
        response_text: Text response from Gemini
    
    Returns:
        dict: Structured advice dictionary
    """
    advice = {
        "overall_advice": "",
        "device_advice": [],
        "insights": []
    }
    
    # Try to extract overall advice (usually at the beginning)
    lines = response_text.split('\n')
    overall_lines = []
    in_overall = False
    
    for line in lines:
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in ['overall', 'summary', 'general', 'assessment']):
            in_overall = True
        if in_overall and line.strip():
            overall_lines.append(line.strip())
            if len(overall_lines) >= 3:  # Take first few sentences
                break
    
    advice["overall_advice"] = " ".join(overall_lines) if overall_lines else "Analysis completed. Please review recommendations."
    
    # Extract insights (look for bullet points or numbered lists)
    for line in lines:
        line_stripped = line.strip()
        if line_stripped.startswith(('-', '*', '•', '1.', '2.', '3.')):
            insight = line_stripped.lstrip('-*•1234567890. ').strip()
            if insight and len(insight) > 10:  # Filter out very short items
                advice["insights"].append(insight)
    
    # If no insights found, add a default
    if not advice["insights"]:
        advice["insights"] = [
            "Sensor data analyzed successfully",
            "Review device-specific recommendations for detailed advice"
        ]
    
    return advice


# ========================================
# Analysis Result Management
# ========================================

def save_analysis_result(analysis_result, user_id):
    """
    Save the latest analysis result to Firestore for a specific user.
    
    Args:
        analysis_result: Analysis result dictionary
        user_id: Firebase user ID
    """
    try:
        db = get_firestore()
        
        # Add a server timestamp and user_id to the new analysis
        analysis_result['analysis_timestamp'] = firestore.SERVER_TIMESTAMP
        analysis_result['user_id'] = user_id
        
        # Save to user-specific collection: /users/{user_id}/analysis_history
        db.collection('users').document(user_id).collection('analysis_history').add(analysis_result)
        
        print(f"  -> Successfully saved analysis to Firestore for user '{user_id}'.")
        
    except Exception as e:
        print(f"  -> ERROR: Could not save analysis to Firestore: {e}")


# ========================================
# Standalone Analysis Function (CLI)
# ========================================

def run_analysis(user_id, time_range_hours=24, limit_per_device=30):
    """
    Main function to run the plant health analysis for a user.
    Analyzes data from all devices belonging to the user.
    
    Args:
        user_id: Firebase user ID (required)
        time_range_hours: Number of hours of data to analyze (default: 24)
        limit_per_device: Maximum readings per device to include (default: 30)
    
    Returns:
        dict: Analysis result or None if failed
    """
    print("\n=== Starting Plant Health Analysis ===\n")
    print(f"Analyzing data for user: {user_id}\n")
    
    try:
        # Prepare data for Gemini
        formatted_data = prepare_data_for_gemini(
            user_id,
            time_range_hours=time_range_hours,
            limit_per_device=limit_per_device
        )
        
        if not formatted_data or formatted_data.get('device_count', 0) == 0:
            print("ERROR: No devices or data found for this user.")
            return None
        
        device_count = formatted_data.get('device_count', 0)
        device_names = [d.get('name', d.get('device_id', 'unknown')) for d in formatted_data.get('devices', [])]
        
        print(f"Analyzing data from {device_count} device(s): {', '.join(device_names)}")
        
        # Load previous analysis history
        analysis_history = load_user_analysis_history(user_id)
        if analysis_history:
            print(f"Loaded {len(analysis_history)} previous analyses for context.")
        
        # Get analysis from Gemini
        print("Requesting analysis from Gemini API...")
        analysis_result = get_gemini_advice(formatted_data, output_format='analysis')
        
        if analysis_result:
            # Print the results
            print("\n--- Plant Health Analysis ---")
            print(f"  Health Score: {analysis_result.get('plant_health_score', 'N/A')} / 10")
            print(f"  Status: {analysis_result.get('status_summary', 'N/A')}")
            print(f"  Trend Analysis: {analysis_result.get('trend_analysis', 'N/A')}")
            print("\n  Recommendations:")
            for rec in analysis_result.get('recommendations', []):
                print(f"    - {rec}")
            print("\n  Ideal Thresholds for Comparison:")
            thresholds = analysis_result.get('ideal_thresholds', {})
            print(f"    - Soil Moisture: {thresholds.get('soil_moisture_percent', 'N/A')}")
            print(f"    - Soil pH: {thresholds.get('soil_ph', 'N/A')}")
            print("---------------------------\n")

            # Save the new analysis to Firestore
            save_analysis_result(analysis_result, user_id)
            
            return analysis_result
        else:
            print("\n=== Analysis Failed ===\n")
            return None
            
    except Exception as e:
        print(f"\n=== Analysis Failed ===\n")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None


# ========================================
# CLI Entry Point
# ========================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Run plant health analysis using sensor data from Firebase for a user'
    )
    parser.add_argument(
        '--user-id',
        type=str,
        required=True,
        help='Firebase user ID (required) - analyzes all devices belonging to this user'
    )
    parser.add_argument(
        '--time-range-hours',
        type=int,
        default=24,
        help='Number of hours of data to analyze (default: 24)'
    )
    parser.add_argument(
        '--limit-per-device',
        type=int,
        default=30,
        help='Maximum readings per device to include (default: 30)'
    )
    args = parser.parse_args()
    
    if not args.user_id:
        print("ERROR: --user-id is required.")
        print("Usage: python app/gemini_client.py --user-id <firebase_user_id>")
        exit(1)
    
    run_analysis(
        user_id=args.user_id,
        time_range_hours=args.time_range_hours,
        limit_per_device=args.limit_per_device
    )

