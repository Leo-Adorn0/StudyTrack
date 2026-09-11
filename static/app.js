/*
AI assistance disclosure: ChatGPT helped create the initial calendar and user
interface interactions. The student reviewed and tested this implementation.
*/

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("form[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!window.confirm(form.dataset.confirm)) {
                event.preventDefault();
            }
        });
    });

    const calendarGrid = document.querySelector("#calendar-grid");
    if (!calendarGrid) {
        return;
    }

    const items = window.studyTrackCalendarItems || [];
    let displayedMonth = new Date();
    displayedMonth = new Date(displayedMonth.getFullYear(), displayedMonth.getMonth(), 1);

    function localDateKey(year, month, day) {
        return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    }

    function renderCalendar() {
        calendarGrid.innerHTML = "";
        const year = displayedMonth.getFullYear();
        const month = displayedMonth.getMonth();
        const firstWeekday = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const today = new Date();

        document.querySelector("#calendar-title").textContent = displayedMonth.toLocaleDateString(
            "en-US",
            { month: "long", year: "numeric" }
        );

        for (let blank = 0; blank < firstWeekday; blank++) {
            const cell = document.createElement("div");
            cell.className = "calendar-day outside";
            calendarGrid.appendChild(cell);
        }

        for (let day = 1; day <= daysInMonth; day++) {
            const cell = document.createElement("div");
            cell.className = "calendar-day";
            const dateKey = localDateKey(year, month, day);

            if (
                day === today.getDate() &&
                month === today.getMonth() &&
                year === today.getFullYear()
            ) {
                cell.classList.add("today");
            }

            const number = document.createElement("span");
            number.className = "day-number";
            number.textContent = day;
            cell.appendChild(number);

            items.filter((item) => item.due_date === dateKey).forEach((item) => {
                const link = document.createElement("a");
                link.className = `calendar-event${item.completed ? " completed" : ""}`;
                link.href = `/items/${item.id}/edit`;
                link.style.borderLeftColor = item.course_color;
                link.textContent = item.title;
                link.title = `${item.course_name}: ${item.title}`;
                cell.appendChild(link);
            });

            calendarGrid.appendChild(cell);
        }
    }

    document.querySelector("#previous-month").addEventListener("click", () => {
        displayedMonth.setMonth(displayedMonth.getMonth() - 1);
        renderCalendar();
    });
    document.querySelector("#next-month").addEventListener("click", () => {
        displayedMonth.setMonth(displayedMonth.getMonth() + 1);
        renderCalendar();
    });
    document.querySelector("#today-month").addEventListener("click", () => {
        const now = new Date();
        displayedMonth = new Date(now.getFullYear(), now.getMonth(), 1);
        renderCalendar();
    });

    renderCalendar();
});
