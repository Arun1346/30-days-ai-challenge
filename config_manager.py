# config_manager.py - Configuration Management System for A.R.I.A Day 27
import json
import os
from typing import Dict, Optional, Any
import logging
import requests

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages API keys and configuration for A.R.I.A voice agent"""
    
    def __init__(self):
        self.user_keys = {}
        self.use_env_keys = True
        self.service_status = {
            'assemblyai': False,
            'gemini': False,
            'murf': False,
            'tavily': False
        }
        
    def set_api_key(self, service: str, key: str):
        """Set API key for a service"""
        if key and len(key.strip()) > 5:
            self.user_keys[service.lower()] = key.strip()
            logger.info(f"API key set for {service}")
            return True
        return False
    
    def get_api_key(self, service: str) -> Optional[str]:
        """Get API key for a service, preferring environment keys if enabled"""
        service_key = service.upper()
        
        # Try environment keys first if enabled
        if self.use_env_keys:
            env_key = os.getenv(f"{service_key}_API_KEY")
            if env_key and len(env_key.strip()) > 5:
                return env_key.strip()
        
        # Fall back to user-provided keys
        return self.user_keys.get(service.lower())
    
    def set_use_env_keys(self, use_env: bool):
        """Toggle between environment and user keys"""
        self.use_env_keys = use_env
        logger.info(f"Use environment keys: {use_env}")
    
    def validate_all_keys(self) -> Dict[str, bool]:
        """Validate all required API keys are present"""
        services = ['assemblyai', 'gemini', 'murf', 'tavily']
        validation_results = {}
        
        for service in services:
            key = self.get_api_key(service)
            validation_results[service] = bool(key and len(key.strip()) > 10)
            
        return validation_results
    
    async def test_api_connection(self, service: str) -> Dict[str, Any]:
        """Test actual API connection for a service"""
        key = self.get_api_key(service)
        if not key:
            return {"connected": False, "error": "No API key provided"}
        
        try:
            if service.lower() == 'assemblyai':
                return await self._test_assemblyai(key)
            elif service.lower() == 'gemini':
                return await self._test_gemini(key)
            elif service.lower() == 'murf':
                return await self._test_murf(key)
            elif service.lower() == 'tavily':
                return await self._test_tavily(key)
            else:
                return {"connected": False, "error": "Unknown service"}
                
        except Exception as e:
            logger.error(f"Error testing {service}: {e}")
            return {"connected": False, "error": str(e)}
    
    async def _test_assemblyai(self, key: str) -> Dict[str, Any]:
        """Test AssemblyAI connection"""
        try:
            response = requests.get(
                "https://api.assemblyai.com/v2/account",
                headers={"authorization": key},
                timeout=10
            )
            
            if response.status_code == 200:
                return {"connected": True, "message": "AssemblyAI connection successful"}
            else:
                return {"connected": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"connected": False, "error": str(e)}
    
    async def _test_gemini(self, key: str) -> Dict[str, Any]:
        """Test Google Gemini connection"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            response = model.generate_content("Hello", 
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=10,
                    temperature=0.1
                ))
            
            if response.text:
                return {"connected": True, "message": "Gemini connection successful"}
            else:
                return {"connected": False, "error": "No response from Gemini"}
                
        except Exception as e:
            return {"connected": False, "error": str(e)}
    
    async def _test_murf(self, key: str) -> Dict[str, Any]:
        """Test Murf AI connection"""
        try:
            response = requests.get(
                "https://api.murf.ai/v1/speech/voices",
                headers={"api-key": key},
                timeout=10
            )
            
            if response.status_code == 200:
                voices = response.json()
                return {"connected": True, "message": f"Murf AI connected ({len(voices)} voices available)"}
            else:
                return {"connected": False, "error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"connected": False, "error": str(e)}
    
    async def _test_tavily(self, key: str) -> Dict[str, Any]:
        """Test Tavily search API connection"""
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=key)
            
            response = client.search(query="test", max_results=1)
            
            if response and 'results' in response:
                return {"connected": True, "message": "Tavily search API connected"}
            else:
                return {"connected": False, "error": "Invalid response from Tavily"}
                
        except Exception as e:
            return {"connected": False, "error": str(e)}
    
    def export_config(self) -> str:
        """Export configuration (without actual keys for security)"""
        config = {
            "services_configured": list(self.user_keys.keys()),
            "use_env_keys": self.use_env_keys,
            "export_timestamp": "2025-08-29T10:10:00Z",
            "version": "Day27_ARIA_Config"
        }
        return json.dumps(config, indent=2)
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get overall configuration status"""
        key_status = self.validate_all_keys()
        return {
            "api_keys": key_status,
            "use_env_keys": self.use_env_keys,
            "total_configured": sum(key_status.values()),
            "overall_health": all(key_status.values()),
            "missing_services": [k for k, v in key_status.items() if not v]
        }

# Global configuration manager instance
config_manager = ConfigManager()
