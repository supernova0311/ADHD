/**
 * NeuroUI — Onboarding Quiz Controller
 * ======================================
 * 6-question adaptive quiz that recommends the best
 * cognitive profile based on user responses.
 */

const TOTAL_QUESTIONS = 6;
let currentQ = 0;
let scores = { adhd: 0, dyslexia: 0, autism: 0 };
let answers = new Array(TOTAL_QUESTIONS).fill(null);

const questions = document.querySelectorAll('.question-card');
const progressFill = document.getElementById('progress-fill');
const btnNext = document.getElementById('btn-next');
const btnBack = document.getElementById('btn-back');
const quizNav = document.getElementById('quiz-nav');
const resultCard = document.getElementById('result-card');

// --- Answer selection ---
document.querySelectorAll('.answer-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const card = btn.closest('.question-card');
    card.querySelectorAll('.answer-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    answers[currentQ] = JSON.parse(btn.dataset.scores);
    btnNext.disabled = false;
  });
});

// --- Next button ---
btnNext.addEventListener('click', () => {
  if (currentQ < TOTAL_QUESTIONS - 1) {
    goToQuestion(currentQ + 1);
  } else {
    showResult();
  }
});

// --- Back button ---
btnBack.addEventListener('click', () => {
  if (currentQ > 0) goToQuestion(currentQ - 1);
});

function goToQuestion(index) {
  questions[currentQ].classList.remove('active');
  currentQ = index;
  questions[currentQ].classList.add('active');

  // Update progress
  progressFill.style.width = ((currentQ + 1) / TOTAL_QUESTIONS * 100) + '%';

  // Update nav
  btnBack.style.visibility = currentQ === 0 ? 'hidden' : 'visible';
  btnNext.textContent = currentQ === TOTAL_QUESTIONS - 1 ? 'See Results \u2192' : 'Next \u2192';
  btnNext.disabled = answers[currentQ] === null;
}

function showResult() {
  // Tally scores
  scores = { adhd: 0, dyslexia: 0, autism: 0 };
  answers.forEach(a => {
    if (a) {
      scores.adhd += a.adhd;
      scores.dyslexia += a.dyslexia;
      scores.autism += a.autism;
    }
  });

  // Find winner
  const max = Math.max(scores.adhd, scores.dyslexia, scores.autism);
  let profile, icon, name, desc;

  if (scores.adhd === max) {
    profile = 'adhd';
    icon = '\u26A1';
    name = 'ADHD Focus Mode';
    desc = 'Your answers suggest you benefit most from distraction removal, content chunking, and key-point highlighting. NeuroUI will strip away visual noise and help you focus on what matters.';
  } else if (scores.dyslexia === max) {
    profile = 'dyslexia';
    icon = '\uD83D\uDCD6';
    name = 'Dyslexia Reading Mode';
    desc = 'Your answers suggest you benefit most from increased spacing, readable fonts, and a reading ruler. NeuroUI will optimize typography and line tracking to reduce visual strain.';
  } else {
    profile = 'autism';
    icon = '\uD83E\uDDD8';
    name = 'Autism Calm Mode';
    desc = 'Your answers suggest you benefit most from calm colors, predictable layouts, and literal language. NeuroUI will reduce sensory stimulation and replace figurative expressions.';
  }

  // Hide questions, show result
  questions.forEach(q => q.classList.remove('active'));
  quizNav.style.display = 'none';
  progressFill.style.width = '100%';

  document.getElementById('result-icon').textContent = icon;
  document.getElementById('result-name').textContent = name;
  document.getElementById('result-desc').textContent = desc;

  const total = scores.adhd + scores.dyslexia + scores.autism || 1;
  document.getElementById('result-scores').innerHTML =
    '<span class="score-pill adhd">ADHD: ' + Math.round(scores.adhd / total * 100) + '%</span>' +
    '<span class="score-pill dyslexia">Dyslexia: ' + Math.round(scores.dyslexia / total * 100) + '%</span>' +
    '<span class="score-pill autism">Autism: ' + Math.round(scores.autism / total * 100) + '%</span>';

  resultCard.classList.add('active');

  // Apply profile button
  document.getElementById('result-action').addEventListener('click', async () => {
    // Store profile-specific default custom settings based on quiz result
    const defaultSettings = {
      adhd: {
        simplification_level: 2,
        distraction_level: 'high',
        spacing_multiplier: 1.2,
        color_mode: 'original',
        font_size: 16,
      },
      dyslexia: {
        simplification_level: 2,
        distraction_level: 'medium',
        spacing_multiplier: 1.8,
        color_mode: 'warm',
        font_size: 18,
      },
      autism: {
        simplification_level: 1,
        distraction_level: 'medium',
        spacing_multiplier: 1.4,
        color_mode: 'muted',
        font_size: 16,
      },
    };

    const settings = defaultSettings[profile] || {
      simplification_level: 2,
      distraction_level: 'medium',
      spacing_multiplier: 1.2,
      color_mode: 'original',
      font_size: 16,
    };

    await chrome.storage.local.set({
      profile: profile,
      quizCompleted: true,
      customSettings: settings,
    });
    window.close();
  });
}
