"""
Adapter Registry for managing LLM provider adapters
Provides centralized registration, discovery, and instantiation of adapters
"""

import os
import time
from typing import Dict, List, Optional, Type, Any
from .base import LLMAdapter
from .google_adapter import GoogleDataStudioAdapter
from .groq_adapter import GroqAdapter
from .litellm_adapter import LiteLLMAdapter
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import ModelInfo


class AdapterRegistry:
    """
    Registry for managing LLM provider adapters.
    
    Provides centralized registration, discovery, and instantiation
    of different provider adapters with configuration management.
    """
    
    def __init__(self):
        self._adapters: Dict[str, Type[LLMAdapter]] = {}
        self._instances: Dict[str, LLMAdapter] = {}
        self._models_cache: Dict[str, List[ModelInfo]] = {}
        self._cache_timestamp: Optional[float] = None
        self._cache_duration = 300  # 5 minutes cache
        self._register_default_adapters()
    
    def _register_default_adapters(self):
        """Register default adapters."""
        self.register("google", GoogleDataStudioAdapter)
        self.register("groq", GroqAdapter)
        self.register("litellm", LiteLLMAdapter)
    
    def register(self, provider_name: str, adapter_class: Type[LLMAdapter]):
        """
        Register an adapter class for a provider.
        
        Args:
            provider_name: Unique identifier for the provider
            adapter_class: Adapter class implementing LLMAdapter interface
        """
        self._adapters[provider_name] = adapter_class
    
    def get_adapter(self, provider_name: str, config: Optional[Dict[str, Any]] = None) -> Optional[LLMAdapter]:
        """
        Get an adapter instance for a provider.
        
        Args:
            provider_name: Provider identifier
            config: Optional configuration for the adapter
            
        Returns:
            LLMAdapter instance or None if provider not found
        """
        if provider_name not in self._adapters:
            return None
        
        # Use cached instance if available and no new config provided
        if provider_name in self._instances and config is None:
            return self._instances[provider_name]
        
        # Create new instance
        adapter_class = self._adapters[provider_name]
        
        # Get configuration from environment if not provided
        if config is None:
            config = self._get_default_config(provider_name)
        
        adapter = adapter_class(config)
        self._instances[provider_name] = adapter
        
        return adapter
    
    def get_all_adapters(self) -> Dict[str, LLMAdapter]:
        """
        Get all registered adapter instances.
        
        Returns:
            Dictionary mapping provider names to adapter instances
        """
        adapters = {}
        
        for provider_name in self._adapters:
            adapter = self.get_adapter(provider_name)
            if adapter:
                adapters[provider_name] = adapter
        
        return adapters
    
    def list_providers(self) -> List[str]:
        """
        List all registered provider names.
        
        Returns:
            List of provider names
        """
        return list(self._adapters.keys())
    
    async def discover_models(self) -> Dict[str, List[ModelInfo]]:
        """
        Discover available models from all registered providers with caching.
        
        Returns:
            Dictionary mapping provider names to their available models
        """
        current_time = time.time()
        
        # Check if cache is valid
        if (self._cache_timestamp and 
            current_time - self._cache_timestamp < self._cache_duration and
            self._models_cache):
            print(f"🔄 Using cached models ({len(self._models_cache)} providers)")
            return self._models_cache
        
        print("🔍 Discovering models from providers...")
        all_models = {}
        
        for provider_name in self._adapters:
            adapter = self.get_adapter(provider_name)
            if adapter:
                try:
                    print(f"   Checking {provider_name}...")
                    models = await adapter.get_models()
                    if models:  # Only include providers with available models
                        all_models[provider_name] = models
                        print(f"   ✅ {provider_name}: {len(models)} models")
                    else:
                        print(f"   ❌ {provider_name}: No models")
                except Exception as e:
                    print(f"   ❌ {provider_name}: Error - {e}")
                    continue
        
        # Update cache
        self._models_cache = all_models
        self._cache_timestamp = current_time
        print(f"✅ Model discovery complete: {sum(len(models) for models in all_models.values())} total models")
        
        return all_models
    
    async def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """
        Get information about a specific model.
        
        Args:
            model_id: Model identifier (can be provider:model format)
            
        Returns:
            ModelInfo if found, None otherwise
        """
        # Parse provider from model_id if present
        if ":" in model_id:
            provider_name, model_name = model_id.split(":", 1)
        else:
            # Search all providers
            all_models = await self.discover_models()
            for provider_models in all_models.values():
                for model in provider_models:
                    if model.id == model_id:
                        return model
            return None
        
        # Get specific provider
        adapter = self.get_adapter(provider_name)
        if not adapter:
            return None
        
        try:
            models = await adapter.get_models()
            for model in models:
                if model.id == model_name or model.id == model_id:
                    return model
        except Exception:
            pass
        
        return None
    
    async def validate_model(self, model_id: str) -> bool:
        """
        Validate if a model is available.
        
        Args:
            model_id: Model identifier to validate
            
        Returns:
            True if model is available
        """
        model_info = await self.get_model_info(model_id)
        return model_info is not None
    
    def _get_default_config(self, provider_name: str) -> Dict[str, Any]:
        """
        Get default configuration for a provider from environment variables.
        
        Args:
            provider_name: Provider identifier
            
        Returns:
            Configuration dictionary
        """
        config = {}
        
        if provider_name == "google":
            config = {
                "api_key": os.getenv("GOOGLE_API_KEY"),
                "base_url": os.getenv("GOOGLE_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")
            }
        
        elif provider_name == "groq":
            config = {
                "api_key": os.getenv("GROQ_API_KEY"),
                "base_url": os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
            }
        
        return config
    
    async def health_check(self) -> Dict[str, bool]:
        """
        Check health status of all registered adapters.
        
        Returns:
            Dictionary mapping provider names to health status
        """
        health_status = {}
        
        for provider_name in self._adapters:
            adapter = self.get_adapter(provider_name)
            if adapter:
                try:
                    # Try to get models as a health check
                    models = await adapter.get_models()
                    health_status[provider_name] = len(models) > 0
                except Exception:
                    health_status[provider_name] = False
            else:
                health_status[provider_name] = False
        
        return health_status
    
    def clear_cache(self):
        """Clear cached adapter instances and models cache."""
        self._instances.clear()
        self._models_cache.clear()
        self._cache_timestamp = None
        print("🗑️ Cleared adapter and models cache")


# Global registry instance
registry = AdapterRegistry()