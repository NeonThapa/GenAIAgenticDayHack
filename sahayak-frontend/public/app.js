// app.js (Final Stable Version)

document.addEventListener('DOMContentLoaded', () => {

    const auth = firebase.auth();
    // IMPORTANT: Make sure this is the correct URL for your App Hosting backend
    const backendUrl = 'https://agile1-e355b.us-central1.run.app'; // Example URL

    const navLinks = document.querySelectorAll('.sidebar-nav .nav-link, .tool-card');
    const views = document.querySelectorAll('.view');
    const allGenerateButtons = document.querySelectorAll('.generate-btn');

    const forms = {
        assessment: { form: document.getElementById('assessment-form'), output: document.getElementById('assessment-output'), task: 'generate_assessment' },
        worksheet: { form: document.getElementById('worksheet-form'), output: document.getElementById('worksheet-output'), task: 'generate_worksheet' },
        lessonPlan: { form: document.getElementById('lesson-plan-form'), output: document.getElementById('lesson-plan-output'), task: 'generate_lesson_plan' },
        contentGen: { form: document.getElementById('content-gen-form'), output: document.getElementById('content-gen-output'), task: 'generate_creative_content' }
    };
    
    function showView(viewId) {
        views.forEach(view => view.classList.toggle('hidden', `view-${viewId}` !== view.id));
        document.querySelectorAll('.nav-link').forEach(link => link.classList.toggle('active', link.dataset.view === viewId));
    }
    navLinks.forEach(link => link.addEventListener('click', (e) => { e.preventDefault(); showView(e.currentTarget.dataset.view); }));

    auth.onAuthStateChanged(user => {
        const authContainer = document.getElementById('auth-container');
        if (user) {
            console.log("Auth State Changed: User is signed IN.");
            authContainer.innerHTML = `<button id="logout-btn">Logout</button>`;
            document.getElementById('logout-btn').addEventListener('click', () => auth.signOut());
            allGenerateButtons.forEach(btn => { btn.disabled = false; });
        } else {
            console.log("Auth State Changed: User is signed OUT.");
            authContainer.innerHTML = ``;
            allGenerateButtons.forEach(btn => { btn.disabled = true; });
            console.log("Attempting automatic sign-in...");
            auth.signInAnonymously().catch(error => {
                console.error("Auto sign-in failed:", error);
                forms.assessment.output.innerHTML = `<p class="error">Authentication failed. Please check your Firebase config and ensure Anonymous Sign-in is enabled in the Firebase console.</p>`;
            });
        }
    });

    async function handleFormSubmit(event, taskName, outputElement) {
        event.preventDefault();
        const form = event.currentTarget;
        const submitButton = form.querySelector('.generate-btn');
        const originalButtonText = submitButton.textContent;
        const user = auth.currentUser;

        if (!user) { alert("Not connected. Please refresh."); return; }

        submitButton.disabled = true;
        submitButton.textContent = 'Generating...';
        outputElement.innerHTML = '<p>Please wait, your request is being processed...</p>';

        try {
            const token = await user.getIdToken();
            const formData = new FormData(form);
            const params = Object.fromEntries(formData.entries());

            if (taskName === 'generate_worksheet' && params.worksheetFile && params.worksheetFile.size > 0) {
                params.worksheetImageBase64 = await toBase64(params.worksheetFile);
                delete params.worksheetFile;
            } else if (taskName === 'generate_worksheet' && !params.worksheetImageBase64) {
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
                case 'generate_worksheet': displayWorksheetImage(jsonData, outputElement); break;
                case 'generate_lesson_plan': displayLessonPlan(jsonData, outputElement); break;
                case 'generate_creative_content': displayCreativeContent(jsonData, outputElement); break;
                default: outputElement.innerHTML = `<p>Unknown task response.</p>`;
            }
        } catch (error) {
            outputElement.innerHTML = `<p class="error">An error occurred: ${error.message}</p>`;
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = originalButtonText;
        }
    }

    Object.values(forms).forEach(f => {
        if (f.form) {
            f.form.addEventListener('submit', (e) => handleFormSubmit(e, f.task, f.output));
        }
    });
    
    const toBase64 = file => new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = error => reject(error);
    });

    function displayAssessment(data, el) {
        el.innerHTML = '<h3>Generated Assessment</h3>';
        if (!data.questions) { el.innerHTML += '<p>Could not generate questions.</p>'; return; }
        data.questions.forEach((q, i) => {
            const qEl = document.createElement('div');
            qEl.className = 'question';
            qEl.innerHTML = `<p><strong>${i + 1}. ${q.question_text}</strong></p><ul>${q.options.map(o => `<li>${o}</li>`).join('')}</ul><p><em>Answer: ${q.correct_answer}</em></p>`;
            el.appendChild(qEl);
        });
    }

    function displayWorksheetImage(data, el) {
        el.innerHTML = '<h3>Generated Worksheet</h3>';
        if (!data.new_image_base64) { el.innerHTML += '<p>Could not generate the new worksheet image.</p>'; return; }
        const img = document.createElement('img');
        img.src = `data:image/png;base64,${data.new_image_base64}`;
        img.style.width = '100%';
        img.style.border = '1px solid #ccc';
        img.style.borderRadius = '8px';
        el.appendChild(img);
    }

    function displayLessonPlan(data, el) {
        el.innerHTML = '<h3>Generated Lesson Plan</h3>';
        const content = document.createElement('div');
        for (const [key, value] of Object.entries(data)) {
            const formattedKey = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            const section = document.createElement('div');
            section.innerHTML = `<h4>${formattedKey}</h4><p>${String(value).replace(/\n/g, '<br>')}</p>`;
            content.appendChild(section);
        }
        el.appendChild(content);
    }

    function displayCreativeContent(data, el) {
        el.innerHTML = '<h3>Generated Creative Content</h3>';
        const img = document.createElement('img');
        img.src = `data:image/png;base64,${data.image_base64}`;
        img.style.maxWidth = '400px';
        img.style.borderRadius = '8px';
        img.style.marginBottom = '1rem';
        const text = document.createElement('p');
        text.textContent = data.creative_text;
        el.appendChild(img);
        el.appendChild(text);
    }
    
    const fileInput = document.getElementById('worksheet-file');
    if (fileInput) { fileInput.addEventListener('change', (e) => { document.querySelector('.file-name').textContent = e.target.files[0] ? e.target.files[0].name : 'No file selected'; }); }

    showView('dashboard');
});