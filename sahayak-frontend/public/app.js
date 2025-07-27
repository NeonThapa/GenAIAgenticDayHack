document.addEventListener('DOMContentLoaded', () => {
    // --- Global References ---
    const auth = firebase.auth();
    const backendUrl = 'https://sahayak-agent-backend-784210616226.us-central1.run.app'; // Your backend URL

    // ... (Navigation and Auth logic remains the same) ...
    const navLinks = document.querySelectorAll('.sidebar-nav .nav-link, .tool-card');
    const views = document.querySelectorAll('.view');
    function showView(viewId) {
        views.forEach(view => view.classList.toggle('hidden', `view-${viewId}` !== view.id));
        document.querySelectorAll('.nav-link').forEach(link => link.classList.toggle('active', link.dataset.view === viewId));
    }
    navLinks.forEach(link => link.addEventListener('click', (e) => { e.preventDefault(); showView(e.currentTarget.dataset.view); }));
    auth.onAuthStateChanged(user => {
        const authContainer = document.getElementById('auth-container');
        if (user) {
            authContainer.innerHTML = `<button id="logout-btn">Logout</button>`;
            document.getElementById('logout-btn').addEventListener('click', () => auth.signOut());
            document.querySelectorAll('.generate-btn').forEach(btn => btn.disabled = false);
        } else {
            authContainer.innerHTML = ``;
            document.querySelectorAll('.generate-btn').forEach(btn => btn.disabled = true);
            auth.signInAnonymously().catch(error => console.error("Auto sign-in failed", error));
        }
    });

    // --- Generic Form Submission Handler ---
    async function handleFormSubmit(event, taskName, outputElement) {
        event.preventDefault();
        const form = event.currentTarget;
        const submitButton = form.querySelector('.generate-btn');
        const user = auth.currentUser;

        if (!user) { alert("Not connected."); return; }

        submitButton.disabled = true;
        submitButton.textContent = 'Generating...';
        outputElement.innerHTML = '<p>Please wait, this may take a moment...</p>';

        try {
            const token = await user.getIdToken();
            const formData = new FormData(form);
            const params = Object.fromEntries(formData.entries());

            // --- NEW: Handle the image file upload ---
            if (taskName === 'generate_worksheet' && params.worksheetFile.size > 0) {
                // Convert the image to a Base64 string
                const imageBase64 = await toBase64(params.worksheetFile);
                params.worksheetImageBase64 = imageBase64; // Add it to the parameters
                delete params.worksheetFile; // Remove the original file object
            } else if (taskName === 'generate_worksheet') {
                throw new Error("Please select an image file to upload.");
            }

            const response = await fetch(backendUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ task: taskName, params: params })
            });

            const responseText = await response.text();
            if (!response.ok) throw new Error(`Server error: ${response.status} - ${responseText}`);
            
            const jsonData = JSON.parse(responseText);
            
            switch(taskName) {
                case 'generate_assessment': displayAssessment(jsonData, outputElement); break;
                case 'generate_worksheet': displayWorksheetImage(jsonData, outputElement); break; // <-- NEW display function
                case 'generate_lesson_plan': displayLessonPlan(jsonData, outputElement); break;
                case 'generate_creative_content': displayCreativeContent(jsonData, outputElement); break;
                default: outputElement.innerHTML = `<p>Unknown task response.</p>`;
            }

        } catch (error) {
            outputElement.innerHTML = `<p class="error">An error occurred: ${error.message}</p>`;
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = `Generate`;
        }
    }

    // --- Attach handlers to forms ---
    const forms = {
        assessment: { form: document.getElementById('assessment-form'), output: document.getElementById('assessment-output'), task: 'generate_assessment' },
        worksheet: { form: document.getElementById('worksheet-form'), output: document.getElementById('worksheet-output'), task: 'generate_worksheet' },
        lessonPlan: { form: document.getElementById('lesson-plan-form'), output: document.getElementById('lesson-plan-output'), task: 'generate_lesson_plan' },
        contentGen: { form: document.getElementById('content-gen-form'), output: document.getElementById('content-gen-output'), task: 'generate_creative_content' }
    };
    Object.values(forms).forEach(f => f.form.addEventListener('submit', (e) => handleFormSubmit(e, f.task, f.output)));

    // --- NEW: Helper function to convert a file to Base64 ---
    const toBase64 = file => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve(reader.result.split(',')[1]); // Get only the Base64 part
        reader.onerror = error => reject(error);
    });

    // --- NEW: Function to display the generated worksheet image ---
    function displayWorksheetImage(data, el) {
        el.innerHTML = '<h3>Generated Worksheet</h3>';
        if (!data.new_image_base64) {
            el.innerHTML += '<p>Could not generate the new worksheet image.</p>';
            return;
        }
        const img = document.createElement('img');
        img.src = `data:image/png;base64,${data.new_image_base64}`;
        img.style.width = '100%';
        img.style.border = '1px solid #ccc';
        img.style.borderRadius = '8px';
        el.appendChild(img);
    }

    // ... (The other display functions remain the same) ...
    function displayAssessment(data, el) { /* ... */ }
    function displayLessonPlan(data, el) { /* ... */ }
    function displayCreativeContent(data, el) { /* ... */ }

    // --- File Input UI Helper ---
    const fileInput = document.getElementById('worksheet-file');
    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            const fileName = e.target.files[0] ? e.target.files[0].name : 'No file selected';
            document.querySelector('.file-name').textContent = fileName;
        });
    }

    showView('dashboard');
});