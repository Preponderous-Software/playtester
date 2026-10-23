# Implementation Plan

This document describes the desired behavior of mocked components and the roadmap for implementing actual functionality.

## Overview

The playtester system is designed with a modular architecture where components can be implemented incrementally. Currently, the AI decision engine and some action executors are mocked to demonstrate the system architecture.

## Component Status

### ✅ Fully Implemented

1. **Screenshot Capture** (`screenshot_capture.py`)
   - Captures full screen
   - Captures specific regions
   - Saves screenshots for debugging
   - **Status**: Fully functional

2. **Core Architecture** (`game_automator.py`)
   - Orchestrates all components
   - Manages automation loop
   - Provides statistics and monitoring
   - **Status**: Fully functional

3. **Base Classes**
   - Abstract base classes for extensibility
   - **Status**: Fully functional

### 🔨 Partially Implemented

4. **Action Executor** (`action_executor.py`)
   - `KeyboardActionExecutor`: Functional for keyboard-based games
   - `MockedActionExecutor`: For testing without actual input
   - **Missing**: 
     - Window focus management
     - Mouse-based action executor
     - Gamepad support
     - Action verification

### 🚧 Mocked / Needs Implementation

5. **AI Decision Engine** (`ai_decision_engine.py`)
   - Current: `MockedAIDecisionEngine` - cycles through actions
   - **Needs**: Integration with actual AI models

6. **Game-Specific Implementations**
   - Ophidian automator (`games/ophidian.py`)
   - Roam automator (`games/roam.py`)
   - **Needs**: Actual game detection, UI analysis, specific action mappings

## Implementation Roadmap

### Phase 1: AI Integration (High Priority)

**Goal**: Replace mocked AI with actual open-source vision-language model

#### Option A: Local Model Integration
Use a local open-source vision-language model:

**Recommended Models**:
1. **LLaVA** (Large Language and Vision Assistant)
   - Open source, good vision understanding
   - Can run locally with reasonable hardware
   - Strong at understanding visual scenes and following instructions

2. **MiniGPT-4**
   - Open source vision-language model
   - Good at image understanding and reasoning

3. **OpenFlamingo**
   - Open source alternative to Flamingo
   - Good few-shot learning capabilities

**Implementation Steps**:
1. Add model dependencies to the `automation` extra (`setup.py`, mirrored in `requirements.txt`)
2. Create model loader and initialization code
3. Implement image preprocessing for model input
4. Create prompt templates for game decision-making
5. Parse model output to extract action decisions
6. Handle confidence scoring

**Code Structure**:
```python
class LocalAIDecisionEngine(AIDecisionEngine):
    def __init__(self, model_name, game_actions):
        self.model = load_model(model_name)
        self.game_actions = game_actions
    
    def analyze_and_decide(self, screenshot, game_context):
        # Preprocess image
        image_tensor = self.preprocess_image(screenshot)
        
        # Create prompt
        prompt = self.create_decision_prompt(game_context)
        
        # Get model decision
        output = self.model(image_tensor, prompt)
        
        # Parse output to action
        action = self.parse_model_output(output)
        return action
```

#### Option B: API-Based Integration
Use open-source AI APIs (e.g., Hugging Face Inference API):

**Implementation Steps**:
1. Set up API credentials
2. Implement API request handling
3. Image encoding for API transmission
4. Rate limiting and error handling
5. Response parsing

### Phase 2: Window Management & Action Verification

**Goal**: Improve action execution reliability

**Features to Implement**:

1. **Window Detection and Focus**
```python
class WindowManager:
    def find_game_window(self, window_title: str):
        """Find game window by title"""
        pass
    
    def focus_window(self, window_handle):
        """Bring window to foreground"""
        pass
    
    def get_window_region(self, window_handle):
        """Get window position and size"""
        pass
```

2. **Action Verification**
```python
def execute_and_verify(self, action, timeout=5.0):
    """Execute action and verify it was received"""
    before = self.capture_state()
    self.execute_action(action)
    after = self.capture_state()
    return self.verify_state_changed(before, after)
```

3. **Input Methods**
   - Mouse click executor for point-and-click games
   - Gamepad support for controller-based games
   - Virtual input for sandboxed environments

### Phase 3: Game-Specific Implementations

**Goal**: Implement actual game detection and control

#### For Ophidian

1. **Research Phase**
   - Understand Ophidian game mechanics
   - Document UI elements and layout
   - Identify action requirements

2. **Implementation**
   - UI element detection (using OpenCV or similar)
   - Game state recognition
   - Specific action sequences
   - Strategy logic

#### For Roam

1. **Research Phase**
   - Understand Roam game mechanics
   - Document UI and navigation
   - Identify objectives and win conditions

2. **Implementation**
   - Environment recognition
   - Navigation logic
   - Interaction handling
   - Objective tracking

### Phase 4: Advanced Features

1. **Learning and Adaptation**
   - Record successful strategies
   - Learn from failures
   - Adapt to different game scenarios

2. **Multi-Game Support**
   - Generic game detection
   - Automatic game type identification
   - Dynamic action mapping

3. **Performance Optimization**
   - Reduce screenshot capture overhead
   - Optimize AI inference time
   - Parallel processing where possible

4. **Monitoring and Debugging**
   - Real-time visualization of decisions
   - Decision explanation (why AI chose action)
   - Performance metrics dashboard

## Testing Strategy

### Current Testing Approach
- `ci/smoke_test.py`, run in CI under Xvfb: real screenshots of a virtual screen and four automation cycles with the mocked engine and executor
- Manual testing with example scripts
- Mocked components for integration testing
- (The agent playtest kit has its own unit and end-to-end suite in `tests/`.)

### Future Testing Requirements

1. **Unit Tests**
   - Test each component independently
   - Mock external dependencies
   - Test edge cases and error handling

2. **Integration Tests**
   - Test component interactions
   - Test full automation cycles
   - Test with different game scenarios

3. **End-to-End Tests**
   - Test with actual games (if available)
   - Test with game simulations
   - Performance benchmarking

## Security and Ethics Considerations

1. **Game Terms of Service**
   - Ensure automation complies with game ToS
   - Document any restrictions
   - Add warnings in documentation

2. **Fair Play**
   - Consider impact on multiplayer games
   - Implement rate limiting
   - Add human-like timing variations

3. **Privacy**
   - Secure storage of screenshots
   - No transmission of sensitive data
   - Clear data retention policies

## Dependencies to Add

For AI integration:
```
# For local model inference
torch>=2.0.0
transformers>=4.30.0
accelerate>=0.20.0

# For image processing
opencv-python>=4.8.0
numpy>=1.24.0

# Optional: for API-based inference
requests>=2.31.0
```

For window management:
```
# Windows
pywin32>=306

# Linux
python-xlib>=0.33
```

## Documentation to Complete

1. **API Reference**
   - Detailed API documentation for each class
   - Parameter descriptions
   - Return value specifications
   - Usage examples

2. **Tutorial Series**
   - Getting started tutorial
   - Creating custom game automators
   - AI model integration guide
   - Troubleshooting guide

3. **Architecture Guide**
   - System architecture diagrams
   - Component interaction flows
   - Extension points documentation

## Contributing Guidelines

When implementing any of these features:

1. Maintain backward compatibility
2. Add comprehensive documentation
3. Include tests for new functionality
4. Update examples as needed
5. Follow existing code style
6. Add type hints for all functions
7. Update this implementation plan

## Success Metrics

The implementation will be considered complete when:

1. ✅ System can capture game screenshots
2. ⏳ AI can make intelligent decisions based on screenshots
3. ⏳ Actions are reliably executed in the target game
4. ⏳ System works with at least one real game (Ophidian or Roam)
5. ⏳ Documentation is comprehensive and clear
6. ⏳ Examples demonstrate real-world usage
7. ⏳ Tests provide good coverage

## Next Steps

**Immediate priorities**:
1. Choose and integrate an open-source AI model
2. Implement window management for reliable action execution
3. Create detailed game analysis for Ophidian or Roam
4. Develop comprehensive tests

**Long-term goals**:
1. Support multiple games with minimal configuration
2. Create a library of pre-trained game strategies
3. Build a community of contributors
4. Establish best practices for ethical game automation
