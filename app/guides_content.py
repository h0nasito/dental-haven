"""Starter patient guides (short educational articles) for the website, one or more per service.

They are added once when the site starts; after that the clinic edits them under
Administration → Website content → Patient guides (edits are never overwritten).
Format: blank line between paragraphs, '## ' for a heading, '- ' for list items.
General education only: no prices, no guarantees, no patient stories.
"""

GUIDES = [
    # ------------------------------------------------------------------ Pediatrics & Special Care
    {
        "slug": "childs-first-dental-visit",
        "service": "pediatric-dentistry",
        "title": "Your child's first dental visit",
        "summary": "When to bring your child in, what happens during the visit, and how to make it a happy first experience.",
        "body": """Your child's first dental visit should happen by their first birthday, or within six months of the first baby tooth coming in. Starting early lets the dentist spot problems while they are small and easy to manage. It also helps your child see the dental clinic as a friendly, familiar place.

## What happens during the visit
The first visit is short and gentle. For very young children, the dentist may examine the teeth while your child sits on your lap.

- A gentle look at the teeth, gums and bite
- A light cleaning, if your child is comfortable
- Fluoride varnish to help protect the teeth, if recommended
- Tips for brushing, feeding and habits like thumb-sucking or pacifier use

## How to prepare your child
- Book a time when your child is usually rested, often in the morning
- Talk about the visit in a positive, simple way ("The dentist will count your teeth!")
- Avoid words like "hurt", "needle" or "drill"
- Bring a favorite toy or blanket for comfort
- Stay calm and relaxed: children pick up on how their parents feel

## After the visit
Most children need a check-up every six months, but your dentist will tell you what's right for your child. Regular visits build good habits and help keep your child's smile healthy as they grow.""",
    },
    {
        "slug": "preventive-dentistry-for-kids",
        "service": "pediatric-dentistry",
        "title": "Why prevention matters: cleanings, fluoride and sealants",
        "summary": "Simple treatments that help stop cavities before they start, and keep your child's visits easy and comfortable.",
        "body": """Preventive dentistry means stopping tooth problems before they begin. It's easier, more comfortable and more affordable to keep teeth healthy than to repair them later. Baby teeth matter too: they help your child eat, speak, and hold space for the adult teeth.

## Oral prophylaxis (professional cleaning)
Even with good brushing, plaque and tartar build up in places that are hard to reach. A professional cleaning removes them and lets the dentist check for early signs of decay. Most children benefit from a cleaning every six months, or as advised by your dentist.

## Fluoride
Fluoride strengthens tooth enamel and helps it resist acid from food and bacteria. It can even help repair very early weak spots before they become cavities. At the clinic, fluoride is painted on as a quick varnish. At home, use a fluoride toothpaste:

- Under 3 years: a smear the size of a grain of rice
- 3 to 6 years: a pea-sized amount
- Supervise brushing and teach your child to spit, not swallow

## Dental sealants
Sealants are thin, protective coatings painted onto the chewing surfaces of the back teeth, where most cavities in children start. They fill the deep grooves so food and bacteria can't get stuck. Applying sealants is quick and painless, with no drilling or injections. They are often placed when the permanent molars come in, around ages 6 and 12.

## Habits that help at home
- Brush twice a day and start flossing when teeth touch
- Limit sweets and sugary drinks, especially between meals
- Avoid putting your child to bed with a bottle of milk or juice
- Keep regular check-ups, even when nothing hurts""",
    },
    {
        "slug": "silver-diamine-fluoride",
        "service": "pediatric-dentistry",
        "title": "Silver diamine fluoride (SDF): stopping cavities without drilling",
        "summary": "A quick, painless liquid treatment that can stop many cavities from growing, often used for young children and patients with special needs.",
        "body": """Silver diamine fluoride, or SDF, is a liquid that is brushed onto a cavity to help stop it from getting bigger. It is quick, painless, and needs no drilling and no injections. This makes it helpful for young children, patients with special needs, and anyone who finds dental treatment difficult.

## How it works
The silver helps kill the bacteria that cause decay, and the fluoride helps harden the tooth. Applied to a cavity, SDF can stop (arrest) the decay in many cases. The treatment takes only a few minutes.

## What to know before treatment
- The decayed part of the tooth turns dark or black permanently. Healthy tooth surfaces are not stained. This can be covered later with a tooth-colored filling if needed.
- It may need to be reapplied at later check-ups, as your dentist advises.
- There may be a brief metallic taste.
- If the liquid touches skin or gums, it can leave a temporary stain that fades on its own.

## Is SDF right for my child?
SDF is not for every cavity. It isn't used for teeth with deep decay that reaches the nerve, infection or ongoing pain, or for people with a silver allergy. Your dentist will check your child's teeth and explain whether SDF, a filling, or another treatment is the best choice.""",
    },
    # ------------------------------------------------------------------ General & Preventive
    {
        "slug": "about-dental-fillings",
        "service": "general-dentistry",
        "title": "Dental fillings: what to expect",
        "summary": "How cavities are repaired with natural-looking, tooth-colored fillings, and how to care for your tooth afterwards.",
        "body": """A cavity is a hole in the tooth caused by decay. Left untreated, it grows deeper and can lead to pain, infection, or the need for a root canal or extraction. A filling removes the decay and restores the tooth's shape and strength, usually in a single visit.

## Signs you may need a filling
- Sensitivity to sweets, cold or hot food and drinks
- A dark spot, hole or rough edge on a tooth
- Food often getting stuck in the same place
- Pain when biting

Many cavities cause no symptoms at first, which is why regular check-ups matter.

## Tooth-colored (composite) fillings
Composite fillings are made of a tooth-colored resin that is matched to the shade of your teeth, so the repair blends in naturally. Because the material bonds to the tooth, the dentist can often keep more of your natural tooth.

## The procedure
- The area is numbed if needed, so you stay comfortable
- The decay is gently removed and the tooth is cleaned
- The filling material is placed in layers and hardened with a special light
- The filling is shaped to your bite and polished

## Aftercare
Wait until the numbness wears off before eating, to avoid biting your cheek or tongue. Mild sensitivity for a few days is normal. If your bite feels high or the sensitivity doesn't improve, let us know. A simple adjustment usually fixes it.""",
    },
    {
        "slug": "white-spots-and-fluorosis",
        "service": "general-dentistry",
        "title": "White spots and fluorosis: gentle, minimally invasive treatment",
        "summary": "What causes white or chalky spots on teeth, and conservative ways to improve them with little or no drilling.",
        "body": """White, chalky or mottled spots on the teeth are common. They can make people feel self-conscious about their smile, but many cases can be improved with gentle treatments that keep your natural tooth structure.

## What causes white spots?
- Early demineralization: the enamel loses minerals because of plaque, often around braces or where brushing is difficult. This is the earliest stage of decay.
- Fluorosis: too much fluoride while the teeth were forming in childhood, causing white streaks or patches. It is cosmetic and not a disease.
- Developmental enamel defects that happen while the teeth are forming.

## Minimally invasive options
The best treatment depends on the cause, how deep the spots are, and your goals. Your dentist may recommend one or a combination of these:

- Remineralization: fluoride varnish and special pastes help restore minerals to early white spots and stop them from progressing.
- Resin infiltration: a thin, fluid resin is drawn into the porous enamel after a gentle surface preparation. It helps the spot blend in with the rest of the tooth, usually with no drilling and no injection.
- Microabrasion: a very thin surface layer of stained enamel is carefully polished away with a mild paste.
- Teeth whitening: can help the spots blend with the surrounding tooth color.

For deeper or larger areas, tooth-colored bonding or veneers may give the best result. Your dentist will examine your teeth and explain the most conservative option for you.""",
    },
    # ------------------------------------------------------------------ Cosmetic & Restorative
    {
        "slug": "veneers-vs-crowns",
        "service": "aesthetic-dentistry",
        "title": "Veneers vs. crowns: what's the difference?",
        "summary": "Both can give you a beautiful, natural-looking smile. Here's how they differ, and when each one is the better choice.",
        "body": """Veneers and crowns are both custom-made to improve how your teeth look. The biggest difference is how much of the tooth they cover, and whether the tooth mainly needs a cosmetic change or needs to be strengthened.

## Veneers
A veneer is a thin shell bonded to the front surface of a tooth. Only a small amount of enamel is usually prepared, and some composite veneers need little or no preparation.

Veneers are a good choice for healthy teeth that you want to look better:
- Discoloration that doesn't respond to whitening
- Chipped or worn edges
- Small gaps between teeth
- Uneven shape or length, or mildly crooked teeth

Veneers can be made from porcelain (strong, stain-resistant and very natural-looking) or composite resin (often done in a single visit and easy to repair).

## Crowns
A crown is a cap that covers the whole tooth, all the way around. The tooth is shaped more than for a veneer so the crown can fit over it.

Crowns are the better choice when a tooth needs protection and strength:
- Large fillings or a lot of missing tooth structure
- Cracked or broken teeth
- Teeth that have had a root canal
- Covering a dental implant or supporting a bridge

Modern crowns can be made from materials like zirconia and all-ceramic, which look natural and are very durable.

## Which one is right for me?
If your tooth is healthy and your goal is a better-looking smile, a veneer is often the more conservative option. If the tooth is weak, heavily filled or broken, a crown protects it better. With good care and regular check-ups, both can last many years. Your dentist will examine your teeth and help you choose the option that fits your smile and your goals.""",
    },
    # ------------------------------------------------------------------ Prosthodontics
    {
        "slug": "caring-for-dentures",
        "service": "prosthodontics",
        "title": "Living with dentures: getting used to them and daily care",
        "summary": "What to expect in the first weeks with new dentures, and simple habits that keep them clean, comfortable and long-lasting.",
        "body": """Dentures replace missing teeth so you can eat, speak and smile with confidence. Complete dentures replace all the teeth in an arch, while partial dentures fill the gaps between your remaining natural teeth.

## The first few weeks
It is normal for new dentures to feel a little strange at first. You may notice extra saliva, mild soreness, or a change in how you speak.

- Start with soft foods cut into small pieces, and chew on both sides
- Read aloud to get used to speaking with your dentures
- Come back for adjustments if you have sore spots; don't try to adjust dentures yourself

## Daily care
- Remove and rinse your dentures after meals
- Brush them every day with a soft brush and a denture cleaner (regular toothpaste can scratch them)
- Soak them overnight in water or a denture solution so they don't dry out, unless your dentist advises otherwise
- Never use hot water, which can warp them
- Handle them over a folded towel or a basin of water in case you drop them
- Clean your gums, tongue and any natural teeth every day

## Regular check-ups
Your gums and jawbone slowly change shape over time, so dentures can become loose. Regular check-ups let your dentist adjust or reline them for a comfortable fit and check the health of your mouth.""",
    },
    # ------------------------------------------------------------------ Implants & Surgery
    {
        "slug": "dental-implants-what-to-expect",
        "service": "dental-implants",
        "title": "Dental implants: what to expect, step by step",
        "summary": "How a missing tooth is replaced with an implant, from the 3D scan to your final crown.",
        "body": """A dental implant replaces the root of a missing tooth. It is a small post placed in the jawbone that supports a natural-looking crown. Implants don't rely on the neighboring teeth for support, and they help preserve the jawbone where a tooth was lost.

## 1. Consultation and planning
Your dentist checks your oral health and takes X-rays, often including a 3D CBCT scan. The scan shows the height and width of the bone and the position of nerves and sinuses, so the implant can be planned precisely.

## 2. Implant placement
The implant is placed under local anesthesia, so the area is numb. Most patients feel pressure rather than pain. Mild swelling or tenderness for a few days afterwards is normal.

## 3. Healing
Over the next few months, the bone bonds with the implant. This is what makes it strong and stable. You may wear a temporary tooth during this time if needed.

## 4. Your new crown
Once healed, a connector (abutment) and a custom crown are attached. The crown is shaped and color-matched to blend in with your smile.

## Caring for your implant
Brush and floss around your implant like a natural tooth, and keep your regular check-ups. Smoking and uncontrolled diabetes can affect healing, so tell your dentist about your health history. Your dentist will let you know if you are a good candidate and whether any other treatment, such as bone grafting, is needed.""",
    },
    # ------------------------------------------------------------------ Orthodontics & TMJ
    {
        "slug": "braces-or-clear-aligners",
        "service": "orthodontics",
        "title": "Braces or clear aligners? Choosing what's right for you",
        "summary": "How traditional braces and clear aligners compare, plus signs of a jaw (TMJ) problem to watch for.",
        "body": """Straight teeth are easier to clean and can help your bite work better, not just look better. Today there are two main ways to straighten teeth: traditional braces and clear aligners.

## Traditional braces
Brackets are attached to the teeth and connected with a wire that is adjusted over time.

- Work well for simple to complex cases
- Fixed in place, so there's nothing to remember to wear
- Need extra care when brushing and some food restrictions (hard and sticky foods)

## Clear aligners
A series of clear, removable trays gradually move the teeth.

- Nearly invisible
- Removed for eating and brushing, so there are no food restrictions
- Must be worn most of the day, typically 20 to 22 hours, to work
- Best for mild to moderate cases

## Which one should I choose?
It depends on your teeth, your bite, your lifestyle and how committed you are to wearing aligners. Your dentist will examine your teeth and explain which options will work for you.

## After treatment: retainers
Teeth tend to move back after treatment, so wearing your retainer as instructed is the key to keeping your new smile.

## Jaw pain and TMJ
The temporomandibular joint (TMJ) connects your jaw to your skull. See your dentist if you notice:
- Clicking, popping or grinding sounds when opening your mouth
- Pain in the jaw, face or around the ear
- Difficulty opening wide, or the jaw locking
- Frequent headaches or teeth grinding

Your dentist can check your bite and recommend care to relieve discomfort.""",
    },
]
