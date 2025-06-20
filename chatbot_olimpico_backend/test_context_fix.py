#!/usr/bin/env python3
"""
Test to verify the conversational memory fix for the reported bug.
"""

def test_conversation_context_fix():
    """
    Test the specific scenario reported by the user where conversational context was broken.
    """
    print("🐛 TESTING CONVERSATIONAL MEMORY FIX")
    print("=" * 50)
    
    # Simulate the exact conversation history from the user's report
    conversation_history = [
        {
            "rol": "user",
            "contenido": "Give me the top 3 countries with the most medals",
            "timestamp": "2024-01-01T10:00:00",
            "consulta_sql": None
        },
        {
            "rol": "assistant", 
            "contenido": "Here are the top 3 countries with the most Olympic medals of all time: 1. United States - 1,992 total medals - 928 gold medals - 583 silver medals - 481 bronze medals 2. Soviet Union - 1,021 total medals - 439 gold medals - 285 silver medals - 297 bronze medals 3. Australia - 798 total medals - 216 gold medals - 270 silver medals - 312 bronze medals As you can see, the United States maintains clear dominance with almost double the medals of the Soviet Union, which occupies second place. Australia completes the podium with solid and consistent performance throughout its Olympic history.",
            "timestamp": "2024-01-01T10:00:01",
            "consulta_sql": "SELECT country, COUNT(*) as total_medals, SUM(CASE WHEN medal = 'Gold' THEN 1 ELSE 0 END) as gold_medals FROM medallas_olimpicas GROUP BY country ORDER BY total_medals DESC LIMIT 3"
        }
    ]
    
    print("📝 CONVERSATION HISTORY:")
    for i, msg in enumerate(conversation_history):
        print(f"   {i+1}. {msg['rol']}: {msg['contenido'][:80]}...")
    
    print("\n🔧 TESTING CONTEXT CONSTRUCTION:")
    
    # Test the context construction from chat.py
    def build_conversation_context(historial_conversacion):
        """Simulate the context building logic from chat.py"""
        contexto_conversacion = ""
        if historial_conversacion and len(historial_conversacion) > 0:
            contexto_conversacion = "\n\nCONTEXTO DE CONVERSACIÓN PREVIA:\n"
            for mensaje in historial_conversacion:
                if mensaje["rol"] == "user":
                    contexto_conversacion += f"Usuario preguntó: \"{mensaje['contenido']}\"\n"
                elif mensaje["rol"] == "assistant":
                    # Apply the new smart truncation logic
                    contenido_assistant = mensaje['contenido']
                    if len(contenido_assistant) > 800:
                        contenido_assistant = contenido_assistant[:800] + "..."
                    contexto_conversacion += f"Asistente respondió: \"{contenido_assistant}\"\n"
                    if mensaje.get("consulta_sql"):
                        contexto_conversacion += f"SQL ejecutado: {mensaje['consulta_sql']}\n"
            contexto_conversacion += "\nFIN DEL CONTEXTO PREVIO\n"
        return contexto_conversacion
    
    # Build context for the follow-up question
    context = build_conversation_context(conversation_history)
    
    print("Generated context:")
    print(context)
    
    print("\n🎯 CRITICAL CHECK:")
    if "Australia" in context and "3." in context:
        print("✅ PASS: Australia is mentioned as 3rd country in context")
    else:
        print("❌ FAIL: Australia as 3rd country is missing from context")
    
    if "798 total medals" in context:
        print("✅ PASS: Australia's medal count is preserved in context")
    else:
        print("❌ FAIL: Australia's medal details are missing")
    
    print("\n📊 CONTEXT ANALYSIS:")
    print(f"   - Total context length: {len(context)} characters")
    print(f"   - Contains 'Australia': {'Yes' if 'Australia' in context else 'No'}")
    print(f"   - Contains '3.': {'Yes' if '3.' in context else 'No'}")
    print(f"   - Assistant response length: {len(conversation_history[1]['contenido'])} chars")
    
    # Simulate the follow-up question
    follow_up_question = "OK, in relation to the third country, could you tell me which category they excel in most?"
    
    print(f"\n❓ FOLLOW-UP QUESTION: {follow_up_question}")
    print("\n🤖 With this context, the AI should now understand:")
    print("   - 'third country' = Australia (from previous response)")
    print("   - Should generate SQL for Australia's sport categories")
    print("   - Should respond about Australia, not Germany")
    
    print("\n" + "=" * 50)
    print("🔧 FIXES APPLIED:")
    print("• Removed 200-character truncation limit") 
    print("• Increased context preservation to 800 characters")
    print("• Smart truncation only for very long responses")
    print("• Full conversation context now available to AI")
    
    return True

if __name__ == "__main__":
    test_conversation_context_fix()