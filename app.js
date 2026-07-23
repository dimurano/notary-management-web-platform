\f1\fs28 \cf0 async function submitNotarialSession() \{\
    // 1. Gather core session and RON metadata\
    const sessionPayload = \{\
        notary_id: "777e4321-e89b-12d3-a456-426614174000", // Hardcoded or pulled from user session profile\
        client_ids: [document.getElementById('selectedClientId').value], // Target signer ID\
        location_type: document.getElementById('locationType').value,   // 'In-Office', 'Mobile', or 'RON'\
        meeting_address: document.getElementById('meetingAddress').value || null,\
        notes: document.getElementById('sessionNotes').value || "",\
        payment_status: document.getElementById('paymentStatus').value || "Unpaid",\
        payment_method: document.getElementById('paymentMethod').value || null,\
        \
        // Extended RON / Electronic Signature Tracking Attributes\
        is_ron: document.getElementById('locationType').value === 'RON',\
        ron_platform: document.getElementById('ronPlatform').value || null,\
        session_audio_video_url: document.getElementById('avRecordingUrl').value || null,\
        tamper_evident_seal_id: document.getElementById('sealId').value || null,\
\
        // 2. Build the list of documents and acts inside this appointment\
        acts: [\
            \{\
                document: \{\
                    document_title: document.getElementById('docTitle').value || "Untitled Document",\
                    page_count: parseInt(document.getElementById('pageCount').value) || 1\
                \},\
                act_type: document.getElementById('actType').value, // e.g., 'Acknowledgment'\
                statutory_fee: parseFloat(document.getElementById('statutoryFee').value) || 0.00,\
                additional_fee: parseFloat(document.getElementById('additionalFee').value) || 0.00,\
                notes: `Signature Type: $\{document.getElementById('signatureType').value\}` // Wet vs. Electronic\
            \}\
        ]\
    \};\
\
    // 3. First upload the document file if one is attached\
    const fileInput = document.getElementById('docFile');\
    if (fileInput.files.length > 0) \{\
        const formData = new FormData();\
        formData.append("file", fileInput.files[0]);\
\
        try \{\
            const uploadResponse = await fetch('http://127.0.0', \{\
                method: 'POST',\
                body: formData\
            \});\
            const uploadResult = await uploadResponse.json();\
            // Bind the returned secure storage hash reference to our document payload\
            sessionPayload.acts[0].document.file_path_hash = uploadResult.file_path_hash;\
        \} catch (err) \{\
            alert("
\f2 \uc0\u9888 \u65039 
\f1  File upload failed. Session record aborted.");\
            return;\
        \}\
    \}\
\
    // 4. Send the complete structured journal entry payload to FastAPI\
    try \{\
        const response = await fetch('http://127.0.0', \{\
            method: 'POST',\
            headers: \{ 'Content-Type': 'application/json' \},\
            body: JSON.stringify(sessionPayload)\
        \});\
\
        if (response.ok) \{\
            const result = await response.json();\
            alert(`
\f2 \uc0\u55356 \u57225 
\f1  Success! Journal Entry recorded. Session ID: $\{result.session_id\}`);\
            window.location.reload(); // Refresh to update dashboards\
        \} else \{\
            const errorData = await response.json();\
            alert(`
\f2 \uc0\u10060 
\f1  Error saving entry: $\{errorData.detail\}`);\
        \}\
    \} catch (err) \{\
        console.error("Network connection failure:", err);\
    \}\
\}}
