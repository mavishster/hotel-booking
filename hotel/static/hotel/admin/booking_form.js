
document.addEventListener("DOMContentLoaded", () => {
    const roomField = document.getElementById("id_room");
    const bedsField = document.getElementById("id_beds");

    if (!roomField || !bedsField) {
        return;
    }

    const optionsUrl = roomField.dataset.bedOptionsUrl;

    if (!optionsUrl) {
        return;
    }

    roomField.addEventListener("change", async () => {
        const roomId = roomField.value;

        bedsField.replaceChildren();

        if (!roomId) {
            return;
        }

        try {
            const url = new URL(optionsUrl, window.location.origin);
            url.searchParams.set("room_id", roomId);

            const response = await fetch(url);

            if (!response.ok) {
                throw new Error("Не удалось загрузить кровати.");
            }

            const beds = await response.json();

            for (const bed of beds) {
                const option = document.createElement("option");
                option.value = bed.id;
                option.textContent = bed.label;
                bedsField.appendChild(option);
            }
        } catch (error) {
            console.error("Ошибка загрузки кроватей:", error);
            alert("Не удалось загрузить кровати. Попробуйте ещё раз.");
        }
    });
});
