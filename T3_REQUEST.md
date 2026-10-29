# T3 — Solidify Handoff Flow as Standard Protocol

The handoff flow has been validated:
- GPT authored HANDOFF.md (26,747 chars)
- Agent uploaded it as a .md file attachment
- New conversation confirmed understanding with all items: yes

Now this flow needs to be solidified as the standard protocol within DevFrame Control Plane, not manual commands.

Specifically, update the project to make this the official T3 task:

1. **Update handoff_generator.py**: Instead of generating thin templates with placeholders, it should produce an interface that clearly marks: "HANDOFF AUTHORSHIP: This section must be written by a GPT/Agent with full project context before transfer. The generator provides the structure; the authoring GPT fills in the substance."

2. **Update conversation_bootstrap.py**: Add support for the "file attachment" mode — uploading HANDOFF.md as a .md file (not inline text paste). The current implementation pastes raw text; the correct flow uses file upload.

3. **Update CLI**: Add `devframe handoff transfer --to new-conversation` command that bundles: verify handoff exists, CDP connect, navigate to new chat, upload as attachment, include bootstrap prompt, send.

4. **Update docs/conversation-bootstrap.md**: Document the official flow: GPT authors handoff, Agent transfers via file attachment, new conversation confirms. Make it clear this is not optional — handoff_verified=false must fail-closed.

5. **Add HANDOFF.md as example**: The one just written serves as the canonical example in examples/context_handoff_g8/.

overall_judgment: accepted | blocked
ready_for_t3_execution: yes | no
t3_scope: as defined above
